"""Backends normalize token usage correctly and never invent counts."""

import json
from types import SimpleNamespace

import anthropic
import httpx
import httpx2  # the HTTP package the Anthropic SDK 2.x uses
import pytest

from promptlab.backends import BackendError, Request
from promptlab.backends.anthropic_backend import AnthropicBackend
from promptlab.backends.anthropic_backend import normalize_usage as anthropic_usage
from promptlab.backends.openai_compat import OpenAICompatBackend
from promptlab.backends.openai_compat import normalize_usage as openai_usage
from promptlab.config import ModelConfig
from promptlab.tokens import INCLUDED_IN_OUTPUT, NOT_REPORTED


def model(**kw):
    base = dict(id="m", display="M", gateway_id="gw-m", family="f", generation=1, api="openai_compat",
                base_url_env="TEST_GATEWAY_URL", api_key_env="TEST_GATEWAY_KEY")
    base.update(kw)
    return ModelConfig(**base)


REQ = Request(messages=[{"role": "user", "content": "hi"}], system="be brief")


# --- OpenAI-compatible --------------------------------------------------------

def test_openai_usage_subtracts_cached_and_keeps_reasoning():
    u = openai_usage({"prompt_tokens": 1000, "completion_tokens": 300,
                      "prompt_tokens_details": {"cached_tokens": 600},
                      "completion_tokens_details": {"reasoning_tokens": 120}}, model(reports_reasoning=True))
    assert (u.input, u.cache_read, u.output, u.reasoning, u.cache_write) == (400, 600, 300, 120, NOT_REPORTED)
    assert u.total_input() == 1000


def test_openai_usage_missing_fields_are_not_reported():
    u = openai_usage({"prompt_tokens": 50, "completion_tokens": 9}, model(reports_reasoning=False))
    assert u.input == 50 and u.cache_read == NOT_REPORTED and u.reasoning == INCLUDED_IN_OUTPUT
    assert openai_usage(None, model()).input == NOT_REPORTED


def ok_body(content="answer", finish="stop"):
    return {"model": "gw-m-2026", "choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5}}


def test_openai_request_shape_and_parse(monkeypatch):
    monkeypatch.setenv("TEST_GATEWAY_URL", "https://gw.internal/v1/")
    monkeypatch.setenv("TEST_GATEWAY_KEY", "k")
    seen = {}

    def handler(request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=ok_body())

    backend = OpenAICompatBackend(client=httpx.Client(transport=httpx.MockTransport(handler)))
    resp = backend.complete(REQ, model(max_tokens_param="max_completion_tokens", max_tokens=77))
    assert seen["url"] == "https://gw.internal/v1/chat/completions"
    assert seen["auth"] == "Bearer k"
    assert seen["body"]["model"] == "gw-m" and seen["body"]["max_completion_tokens"] == 77
    assert "max_tokens" not in seen["body"] and "temperature" not in seen["body"]
    assert seen["body"]["messages"][0] == {"role": "system", "content": "be brief"}
    assert (resp.text, resp.stop, resp.usage.input, resp.served_model) == ("answer", "end", 20, "gw-m-2026")


def test_openai_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("TEST_GATEWAY_URL", "https://gw.internal/v1")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(429, text="slow down") if calls["n"] < 3 else httpx.Response(200, json=ok_body())

    sleeps = []
    backend = OpenAICompatBackend(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=sleeps.append)
    assert backend.complete(REQ, model()).text == "answer"
    assert calls["n"] == 3 and sleeps == [1, 2]


def test_openai_does_not_retry_client_errors(monkeypatch):
    monkeypatch.setenv("TEST_GATEWAY_URL", "https://gw.internal/v1")
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(400, text="bad model")

    backend = OpenAICompatBackend(client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    with pytest.raises(BackendError, match="HTTP 400"):
        backend.complete(REQ, model())
    assert calls["n"] == 1


def test_openai_needs_a_url(monkeypatch):
    monkeypatch.delenv("TEST_GATEWAY_URL", raising=False)
    with pytest.raises(BackendError, match="TEST_GATEWAY_URL"):
        OpenAICompatBackend(client=httpx.Client()).complete(REQ, model())


def test_openai_length_and_refusal(monkeypatch):
    monkeypatch.setenv("TEST_GATEWAY_URL", "https://gw.internal/v1")
    bodies = iter([ok_body(finish="length"), {"choices": [{"message": {"content": None, "refusal": "no"},
                                                           "finish_reason": "stop"}]}])
    backend = OpenAICompatBackend(client=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json=next(bodies)))))
    assert backend.complete(REQ, model()).stop == "max_tokens"
    refused = backend.complete(REQ, model())
    assert refused.stop == "refusal" and refused.text == "no"


# --- Anthropic ----------------------------------------------------------------

def test_anthropic_usage_fields():
    u = anthropic_usage(SimpleNamespace(input_tokens=40, output_tokens=900, cache_read_input_tokens=1000,
                                        cache_creation_input_tokens=0,
                                        output_tokens_details=SimpleNamespace(thinking_tokens=700)))
    assert (u.input, u.output, u.reasoning, u.cache_read, u.cache_write) == (40, 900, 700, 1000, 0)
    assert u.total_input() == 1040


def test_anthropic_usage_without_thinking_detail():
    u = anthropic_usage(SimpleNamespace(input_tokens=5, output_tokens=6, cache_read_input_tokens=None,
                                        cache_creation_input_tokens=None))
    assert u.reasoning == INCLUDED_IN_OUTPUT and u.cache_read == NOT_REPORTED


def sse(*events):
    return "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)


def stream_body(stop_reason="end_turn"):
    message = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5", "content": [],
               "stop_reason": None, "stop_sequence": None,
               "usage": {"input_tokens": 12, "output_tokens": 1, "cache_read_input_tokens": 0,
                         "cache_creation_input_tokens": 0}}
    return sse(
        ("message_start", {"type": "message_start", "message": message}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "text", "text": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "text_delta", "text": "Hello"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                           "usage": {"output_tokens": 7}}),
        ("message_stop", {"type": "message_stop"}),
    )


def anthropic_backend(handler):
    client = anthropic.Anthropic(api_key="test", base_url="https://api.test",
                                 http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)
    return AnthropicBackend(client=client)


def test_anthropic_request_shape_and_stream_parse():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, text=stream_body(), headers={"content-type": "text/event-stream"})

    resp = anthropic_backend(handler).complete(REQ, model(api="anthropic", gateway_id="claude-opus-5"))
    body = seen["body"]
    assert body["model"] == "claude-opus-5" and body["system"] == "be brief"
    assert "temperature" not in body and "fallbacks" not in body and "output_config" not in body
    assert (resp.text, resp.stop, resp.usage.input, resp.usage.output) == ("Hello", "end", 12, 7)


def test_anthropic_effort_only_when_configured():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx2.Response(200, text=stream_body(), headers={"content-type": "text/event-stream"})

    anthropic_backend(handler).complete(REQ, model(api="anthropic", effort="high"))
    assert seen["body"]["output_config"] == {"effort": "high"}


def test_anthropic_refusal_and_errors():
    refusal = anthropic_backend(lambda r: httpx2.Response(200, text=stream_body("refusal"),
                                                          headers={"content-type": "text/event-stream"}))
    assert refusal.complete(REQ, model(api="anthropic")).stop == "refusal"
    failing = anthropic_backend(lambda r: httpx2.Response(404, json={"type": "error", "error": {
        "type": "not_found_error", "message": "model not found"}}))
    with pytest.raises(BackendError, match="404"):
        failing.complete(REQ, model(api="anthropic"))


def test_anthropic_missing_credentials_is_a_backend_error(monkeypatch, tmp_path):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "TEST_GATEWAY_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no SDK profile on disk
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(BackendError, match="no credentials"):
        AnthropicBackend().complete(REQ, model(api="anthropic", base_url_env=None))
