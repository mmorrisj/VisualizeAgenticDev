"""Anthropic Messages API backend, through the official SDK.

Measurement choices, deliberately different from production defaults:

- No sampling parameters (temperature, top_p) are sent. Current Claude models
  reject them, so every model in the study runs at its own defaults.
- No server-side refusal fallback. A fallback would answer with a different
  model and blur the measurement; a refusal is recorded as stop="refusal".
- Effort is sent only when models.yaml fixes one for that model, and is
  recorded with the run.

The endpoint can be Anthropic's API or a gateway (`base_url_env`). Credentials
come from the environment variable named in `api_key_env`, or the SDK's own
credential resolution when that is unset.
"""

from __future__ import annotations

import os
import time

import anthropic

from ..config import ModelConfig
from ..tokens import INCLUDED_IN_OUTPUT, NOT_REPORTED, Usage, int_or_none
from .base import BackendError, Request, Response

STOP_MAP = {"end_turn": "end", "stop_sequence": "end", "max_tokens": "max_tokens",
            "refusal": "refusal", "tool_use": "tool_use"}


def normalize_usage(usage) -> Usage:
    """Map the SDK's usage object onto Usage.

    input_tokens is already uncached input. Thinking is billed as output; when
    the response itemizes it (output_tokens_details.thinking_tokens) it is
    recorded, otherwise it is marked as included in output.
    """
    if usage is None:
        return Usage()
    details = getattr(usage, "output_tokens_details", None)
    thinking = int_or_none(getattr(details, "thinking_tokens", None)) if details is not None else None

    def count(name):
        value = int_or_none(getattr(usage, name, None))
        return value if value is not None else NOT_REPORTED

    return Usage(
        input=count("input_tokens"),
        output=count("output_tokens"),
        reasoning=thinking if thinking is not None else INCLUDED_IN_OUTPUT,
        cache_read=count("cache_read_input_tokens"),
        cache_write=count("cache_creation_input_tokens"),
    )


class AnthropicBackend:
    def __init__(self, client: anthropic.Anthropic | None = None):
        self._client = client
        self._clients: dict[tuple, anthropic.Anthropic] = {}

    def _client_for(self, model: ModelConfig) -> anthropic.Anthropic:
        if self._client is not None:
            return self._client
        base_url = os.environ.get(model.base_url_env or "", "") or None
        key = os.environ.get(model.api_key_env or "", "") or None
        cache_key = (base_url, key)
        if cache_key not in self._clients:
            kwargs = {"max_retries": 3}
            if base_url:
                kwargs["base_url"] = base_url
            if key:
                kwargs["api_key"] = key
            self._clients[cache_key] = anthropic.Anthropic(**kwargs)
        return self._clients[cache_key]

    def complete(self, request: Request, model: ModelConfig) -> Response:
        params = {"model": model.gateway_id, "max_tokens": model.max_tokens, "messages": request.messages}
        if request.system:
            params["system"] = request.system
        if request.tools:
            params["tools"] = request.tools
        if model.effort:
            params["output_config"] = {"effort": model.effort}
        start = time.perf_counter()
        try:
            # Streaming avoids HTTP timeouts on long outputs; the final message has the usage.
            with self._client_for(model).messages.stream(**params) as stream:
                message = stream.get_final_message()
        except anthropic.APIStatusError as err:
            raise BackendError(f"{model.id}: HTTP {err.status_code}: {err.message}") from err
        except anthropic.APIConnectionError as err:
            raise BackendError(f"{model.id}: connection error: {err}") from err
        except TypeError as err:
            # The SDK raises TypeError when it finds no credentials at all.
            if "authentication" not in str(err):
                raise
            raise BackendError(f"{model.id}: no credentials: set {model.api_key_env} "
                               "or configure the SDK's credentials") from err
        latency = time.perf_counter() - start
        content = [content_block(block) for block in message.content]
        text = "".join(b["text"] for b in content if b["type"] == "text")
        reason = message.stop_reason or ""
        return Response(text=text, usage=normalize_usage(message.usage), stop=STOP_MAP.get(reason, f"other:{reason}"),
                        latency_s=latency, served_model=getattr(message, "model", "") or "", content=content)


def content_block(block) -> dict:
    """An SDK content block as a plain dict that can be sent back in the next request.

    Text and tool calls are rebuilt with only the fields the API accepts back.
    Anything else (thinking blocks and their signatures) is kept whole, because
    the API needs it returned unchanged during tool use.
    """
    kind = getattr(block, "type", "")
    if kind == "text":
        return {"type": "text", "text": block.text}
    if kind == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": dict(block.input or {})}
    return block.model_dump(exclude_none=True)
