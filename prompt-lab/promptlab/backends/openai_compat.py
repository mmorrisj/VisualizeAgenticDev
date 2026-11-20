"""OpenAI-compatible chat completions backend.

This is the shape most internal gateways expose, for Llama and GPT models alike.
The endpoint URL and key come from the environment variables named in
models.yaml (`base_url_env`, `api_key_env`); nothing secret is stored in config.
"""

from __future__ import annotations

import os
import time

import httpx

from ..config import ModelConfig
from ..tokens import INCLUDED_IN_OUTPUT, NOT_REPORTED, Usage, int_or_none
from .base import BackendError, Request, Response

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4

STOP_MAP = {"stop": "end", "length": "max_tokens", "content_filter": "refusal", "tool_calls": "end"}


def normalize_usage(usage: dict | None, model: ModelConfig) -> Usage:
    """Map an OpenAI-style usage object onto Usage.

    prompt_tokens includes cached tokens, so uncached input = prompt - cached.
    Reasoning tokens, where reported, are already part of completion_tokens.
    """
    if not usage:
        return Usage()
    prompt = int_or_none(usage.get("prompt_tokens"))
    completion = int_or_none(usage.get("completion_tokens"))
    cached = int_or_none((usage.get("prompt_tokens_details") or {}).get("cached_tokens"))
    reasoning = int_or_none((usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
    if reasoning is None:
        reasoning_value = INCLUDED_IN_OUTPUT if model.reports_reasoning is False else NOT_REPORTED
    else:
        reasoning_value = reasoning
    return Usage(
        input=(prompt - (cached or 0)) if prompt is not None else NOT_REPORTED,
        output=completion if completion is not None else NOT_REPORTED,
        reasoning=reasoning_value,
        cache_read=cached if cached is not None else NOT_REPORTED,
        cache_write=NOT_REPORTED,  # the OpenAI shape does not report cache writes
    )


class OpenAICompatBackend:
    def __init__(self, client: httpx.Client | None = None, sleep=time.sleep):
        self._client = client or httpx.Client(timeout=httpx.Timeout(600.0, connect=10.0))
        self._sleep = sleep

    def complete(self, request: Request, model: ModelConfig) -> Response:
        base_url = os.environ.get(model.base_url_env or "", "")
        if not base_url:
            raise BackendError(f"{model.id}: set {model.base_url_env} to the gateway URL")
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(model.api_key_env or "", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        messages = ([{"role": "system", "content": request.system}] if request.system else []) + request.messages
        body = {"model": model.gateway_id, "messages": messages, model.max_tokens_param: model.max_tokens}

        url = base_url.rstrip("/") + "/chat/completions"
        last_error = ""
        for attempt in range(MAX_ATTEMPTS):
            start = time.perf_counter()
            try:
                resp = self._client.post(url, json=body, headers=headers)
            except httpx.HTTPError as err:
                last_error = f"connection error: {err}"
            else:
                latency = time.perf_counter() - start
                if resp.status_code == 200:
                    return self._parse(resp.json(), model, latency)
                last_error = f"HTTP {resp.status_code}: {resp.text[:300]}"
                if resp.status_code not in RETRY_STATUS:
                    break
            if attempt < MAX_ATTEMPTS - 1:
                self._sleep(min(2 ** attempt, 20))
        raise BackendError(f"{model.id}: {last_error}")

    @staticmethod
    def _parse(data: dict, model: ModelConfig, latency: float) -> Response:
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        finish = choice.get("finish_reason") or ""
        text = message.get("content") or ""
        stop = STOP_MAP.get(finish, f"other:{finish}")
        if message.get("refusal"):
            text, stop = message["refusal"], "refusal"
        return Response(text=text, usage=normalize_usage(data.get("usage"), model), stop=stop,
                        latency_s=latency, served_model=data.get("model", ""))
