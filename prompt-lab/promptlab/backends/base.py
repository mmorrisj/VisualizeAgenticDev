"""The interface every backend implements (spec section 11.2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..config import ModelConfig
from ..tokens import Usage


@dataclass
class Request:
    """One model request. One-shot mode sends a single user message."""

    messages: list[dict]                 # Anthropic Messages shape; one-shot sends a single user string
    system: str | None = None
    meta: dict = field(default_factory=dict)  # task id, variant, etc.; used by mock and replay
    tools: list[dict] | None = None      # harness mode: [{"name", "description", "input_schema"}]


@dataclass
class Response:
    text: str
    usage: Usage
    stop: str                 # "end", "tool_use", "max_tokens", "refusal", or "other:<provider value>"
    latency_s: float
    served_model: str = ""    # the model name the provider says answered
    # Content blocks in the Anthropic shape: {"type": "text", "text"} and
    # {"type": "tool_use", "id", "name", "input"}. Harness mode reads these.
    content: list[dict] = field(default_factory=list)

    @property
    def tool_calls(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class BackendError(RuntimeError):
    """A request that could not be completed (after retries)."""


class Backend(Protocol):
    def complete(self, request: Request, model: ModelConfig) -> Response: ...
