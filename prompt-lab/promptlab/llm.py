"""Helpers for the lab's own model calls: the generator, the judge, the simulated requester.

These calls ask for JSON in the prompt and validate the reply here, rather than
using one provider's structured-output feature, so any model on the gateway can
act as judge. A reply that does not validate is retried once with the error.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .backends import BackendError, Request, Response, backend_for
from .config import ModelConfig

T = TypeVar("T", bound=BaseModel)


def ask(model: ModelConfig, system: str, user: str, meta: dict | None = None) -> Response:
    request = Request(messages=[{"role": "user", "content": user}], system=system, meta=meta or {})
    return backend_for(model).complete(request, model)


def first_json_object(text: str) -> dict:
    """The first {...} object in the text, tolerating Markdown fences and prose around it."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    start = text.find("{")
    while start != -1:
        depth, in_str, escape = 0, False, False
        for i, ch in enumerate(text[start:], start):
            if in_str:
                escape = (ch == "\\") and not escape
                if ch == '"' and not escape:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
        start = text.find("{", start + 1) if not candidates else -1
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("no JSON object found in the reply")


class Structured:
    """The result of ask_json: the parsed object (or None), every response, and any error."""

    def __init__(self, value, responses: list[Response], error: str = ""):
        self.value = value
        self.responses = responses
        self.error = error


def ask_json(model: ModelConfig, system: str, user: str, schema: type[T], meta: dict | None = None,
             extra_check: Callable[[T], str] | None = None) -> Structured:
    """Ask for JSON matching `schema`. One retry, which tells the model what was wrong.

    `extra_check` returns an error message (or "") for problems the schema cannot
    express, such as a quote that does not appear in the text being judged.
    """
    responses: list[Response] = []
    prompt = user
    error = ""
    for attempt in range(2):
        try:
            response = ask(model, system, prompt, {**(meta or {}), "attempt": attempt})
        except BackendError as err:
            return Structured(None, responses, str(err))
        responses.append(response)
        try:
            value = schema.model_validate(first_json_object(response.text))
            error = extra_check(value) if extra_check else ""
            if not error:
                return Structured(value, responses)
        except (ValueError, ValidationError) as err:
            error = str(err)[:600]
        prompt = (f"{user}\n\nYour previous reply could not be used: {error}\n"
                  "Reply again with only the corrected JSON object.")
    return Structured(None, responses, error)
