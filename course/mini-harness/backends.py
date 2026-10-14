"""Model backends for mini-harness. Standard library only.

Every backend takes the same inputs (system prompt, tool definitions, message
history) and returns the same shape:

    {
        "content": [ {"type": "text", "text": ...},
                     {"type": "tool_use", "id": ..., "name": ..., "input": {...}} ],
        "stop_reason": "tool_use" | "end_turn",
        "usage": {"input_tokens": int, "output_tokens": int,
                  "cache_read_tokens": int, "cache_write_tokens": int},
        "estimated": bool,     # True when token counts are estimates
    }

Internally, messages use the Anthropic Messages API shape. The OpenAI-compatible
backend converts to and from the chat-completions shape, which is what most
self-hosted model servers (vLLM, llama.cpp server, Ollama, LiteLLM) expose.
"""
from __future__ import annotations

import http.client
import json
import ssl
import time
import urllib.error
import urllib.request


def estimate_tokens(obj) -> int:
    """Rough token estimate: about 4 characters per token for English and code."""
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return max(1, len(text) // 4)


class BackendError(RuntimeError):
    pass


# --------------------------------------------------------------------------
# Mock backend: replays a scripted scenario. No network, no model.
# --------------------------------------------------------------------------
class MockBackend:
    """Replays responses from a scenario file, one per request.

    The script does not react to what the tools return, or to denials. A real
    model would read each tool result and adapt; the mock shows the mechanics
    of the loop with deterministic output.
    """

    name = "mock"

    def __init__(self, scenario_path: str, model: str = "mock-model"):
        with open(scenario_path, encoding="utf-8") as fh:
            self.scenario = json.load(fh)
        self.responses = list(self.scenario["responses"])
        self.model = model

    def complete(self, system: str, tools: list, messages: list) -> dict:
        request = {"system": system, "tools": tools, "messages": messages}
        if self.responses:
            content = self.responses.pop(0)
        else:
            content = [{"type": "text", "text": "[mock scenario finished]"}]
        stop = "tool_use" if any(b["type"] == "tool_use" for b in content) else "end_turn"
        time.sleep(0.05)  # make the loop visible
        return {
            "content": content,
            "stop_reason": stop,
            "usage": {
                "input_tokens": estimate_tokens(request),
                "output_tokens": estimate_tokens(content),
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            },
            "estimated": True,
        }


# --------------------------------------------------------------------------
# Shared HTTP helper
# --------------------------------------------------------------------------
def _post_json(url: str, body: dict, headers: dict, ca_file: str | None, timeout: int) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("content-type", "application/json")
    for key, value in headers.items():
        req.add_header(key, value)
    context = ssl.create_default_context(cafile=ca_file) if ca_file else None
    try:
        # urllib honors HTTPS_PROXY / NO_PROXY from the environment.
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")[:500]
        raise BackendError(f"HTTP {err.code} from {url}: {detail}") from err
    except urllib.error.URLError as err:
        raise BackendError(f"Could not reach {url}: {err.reason}") from err
    except (OSError, http.client.HTTPException) as err:
        raise BackendError(f"Connection to {url} failed: {err!r}") from err
    except json.JSONDecodeError as err:
        raise BackendError(f"{url} did not return JSON: {err}") from err


def _auth_headers(api_key: str | None, auth_style: str) -> dict:
    if not api_key:
        return {}
    if auth_style == "bearer":
        return {"authorization": f"Bearer {api_key}"}
    return {"x-api-key": api_key}


# --------------------------------------------------------------------------
# Anthropic Messages API (direct, or an internal gateway that speaks it)
# --------------------------------------------------------------------------
class AnthropicBackend:
    name = "anthropic"

    def __init__(self, base_url, model, api_key=None, auth_style="x-api-key",
                 ca_file=None, max_tokens=4096, timeout=300):
        self.url = base_url.rstrip("/") + "/messages"
        self.model = model
        self.headers = {"anthropic-version": "2023-06-01", **_auth_headers(api_key, auth_style)}
        self.ca_file, self.max_tokens, self.timeout = ca_file, max_tokens, timeout

    def complete(self, system: str, tools: list, messages: list) -> dict:
        body = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "tools": tools,
            "messages": messages,
        }
        raw = _post_json(self.url, body, self.headers, self.ca_file, self.timeout)
        usage = raw.get("usage", {})
        return {
            "content": raw.get("content", []),
            "stop_reason": raw.get("stop_reason", "end_turn"),
            "usage": {
                "input_tokens": usage.get("input_tokens", 0),
                "output_tokens": usage.get("output_tokens", 0),
                "cache_read_tokens": usage.get("cache_read_input_tokens", 0) or 0,
                "cache_write_tokens": usage.get("cache_creation_input_tokens", 0) or 0,
            },
            "estimated": False,
        }


# --------------------------------------------------------------------------
# OpenAI-compatible chat completions (most self-hosted model servers)
# --------------------------------------------------------------------------
class OpenAICompatBackend:
    name = "openai"

    def __init__(self, base_url, model, api_key=None, auth_style="bearer",
                 ca_file=None, max_tokens=4096, timeout=300):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.headers = _auth_headers(api_key, auth_style)
        self.ca_file, self.max_tokens, self.timeout = ca_file, max_tokens, timeout

    @staticmethod
    def _to_openai(system: str, tools: list, messages: list):
        out = [{"role": "system", "content": system}]
        for msg in messages:
            content = msg["content"]
            if isinstance(content, str):
                out.append({"role": msg["role"], "content": content})
                continue
            if msg["role"] == "assistant":
                text = "".join(b.get("text", "") for b in content if b["type"] == "text")
                calls = [
                    {"id": b["id"], "type": "function",
                     "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                    for b in content if b["type"] == "tool_use"
                ]
                entry = {"role": "assistant", "content": text or None}
                if calls:
                    entry["tool_calls"] = calls
                out.append(entry)
            else:
                for block in content:
                    if block["type"] == "tool_result":
                        out.append({"role": "tool", "tool_call_id": block["tool_use_id"],
                                    "content": block["content"]})
                    elif block["type"] == "text":
                        out.append({"role": "user", "content": block["text"]})
        oa_tools = [
            {"type": "function",
             "function": {"name": t["name"], "description": t["description"],
                          "parameters": t["input_schema"]}}
            for t in tools
        ]
        return out, oa_tools

    def complete(self, system: str, tools: list, messages: list) -> dict:
        oa_messages, oa_tools = self._to_openai(system, tools, messages)
        body = {"model": self.model, "max_tokens": self.max_tokens,
                "messages": oa_messages, "tools": oa_tools}
        raw = _post_json(self.url, body, self.headers, self.ca_file, self.timeout)
        choice = raw["choices"][0]
        message = choice["message"]
        content = []
        if message.get("content"):
            content.append({"type": "text", "text": message["content"]})
        for call in message.get("tool_calls") or []:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_unparseable_arguments": call["function"].get("arguments")}
            content.append({"type": "tool_use", "id": call["id"],
                            "name": call["function"]["name"], "input": args})
        usage = raw.get("usage", {})
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        prompt = usage.get("prompt_tokens", 0)
        return {
            "content": content,
            "stop_reason": "tool_use" if message.get("tool_calls") else "end_turn",
            "usage": {
                # Report uncached input separately, the way the Anthropic API does.
                "input_tokens": prompt - cached,
                "output_tokens": usage.get("completion_tokens", 0),
                "cache_read_tokens": cached,
                "cache_write_tokens": 0,
            },
            "estimated": False,
        }


def make_backend(args):
    if args.backend == "mock":
        if not args.scenario:
            raise SystemExit("--backend mock needs --scenario <file>")
        return MockBackend(args.scenario)
    if not args.base_url or not args.model:
        raise SystemExit(f"--backend {args.backend} needs --base-url and --model")
    common = dict(base_url=args.base_url, model=args.model, api_key=args.api_key,
                  ca_file=args.ca_file, max_tokens=args.max_tokens)
    if args.backend == "anthropic":
        return AnthropicBackend(auth_style=args.auth_style or "x-api-key", **common)
    return OpenAICompatBackend(auth_style=args.auth_style or "bearer", **common)
