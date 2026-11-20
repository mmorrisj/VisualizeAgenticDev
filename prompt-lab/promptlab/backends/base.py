"""The interface every backend implements (spec section 11.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..config import ModelConfig
from ..tokens import Usage


@dataclass
class Request:
    """One model request. One-shot mode sends a single user message."""

    messages: list[dict]                 # [{"role": "user" | "assistant", "content": str}]
    system: str | None = None
    meta: dict = field(default_factory=dict)  # task id, variant, etc.; used by mock and replay


@dataclass
class Response:
    text: str
    usage: Usage
    stop: str                 # "end", "max_tokens", "refusal", or "other:<provider value>"
    latency_s: float
    served_model: str = ""    # the model name the provider says answered


class BackendError(RuntimeError):
    """A request that could not be completed (after retries)."""


class Backend(Protocol):
    def complete(self, request: Request, model: ModelConfig) -> Response: ...
