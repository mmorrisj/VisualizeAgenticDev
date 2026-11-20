"""Backends: one interface for every model source (spec section 11.2)."""

from __future__ import annotations

from ..config import ModelConfig
from .base import Backend, BackendError, Request, Response

__all__ = ["Backend", "BackendError", "Request", "Response", "backend_for"]

_instances: dict[str, Backend] = {}


def backend_for(model: ModelConfig) -> Backend:
    """One shared backend instance per API style. Imports are lazy so the mock
    backend works without network libraries configured."""
    if model.api not in _instances:
        if model.api == "mock":
            from .mock import MockBackend
            _instances[model.api] = MockBackend()
        elif model.api == "openai_compat":
            from .openai_compat import OpenAICompatBackend
            _instances[model.api] = OpenAICompatBackend()
        elif model.api == "anthropic":
            from .anthropic_backend import AnthropicBackend
            _instances[model.api] = AnthropicBackend()
        else:  # pragma: no cover - pydantic restricts the values
            raise BackendError(f"unknown api style: {model.api}")
    return _instances[model.api]
