"""Deterministic mock backend, for engine tests and development without a model.

It answers from each task's prepared answers (tasks/<task>/answers/), so a run
exercises extraction and checks on real-looking output. A model's
`mock_quality` decides which answer it gives:

- high: the good answer for every prompt variant;
- low:  the bad answer for terse prompts, the good answer once the prompt is
        informed. This mimics the pattern the study looks for, but it is a
        script, not evidence: results from mock models are labelled synthetic.

Token counts use the course estimator and are marked synthetic.
"""

from __future__ import annotations

import time

from ..config import ModelConfig
from ..tasks import load_task
from ..tokens import NOT_REPORTED, Usage, estimate_tokens
from .base import BackendError, Request, Response

INFORMED_VARIANTS = {"informed", "full", "ai-interviewed"}


class MockBackend:
    def complete(self, request: Request, model: ModelConfig) -> Response:
        task_id = request.meta.get("task")
        variant = request.meta.get("variant", "")
        if not task_id:
            raise BackendError("mock backend needs request.meta['task']")
        task = load_task(task_id)
        good = model.mock_quality == "high" or variant in INFORMED_VARIANTS
        kind = "good" if good else "bad"
        names = [n for n in task.answers() if n.startswith(kind)]
        if not names:
            raise BackendError(f"task {task_id} has no '{kind}' answer for the mock backend")
        text = task.answer(names[0])
        start = time.perf_counter()
        usage = Usage(
            input=estimate_tokens({"system": request.system, "messages": request.messages}),
            output=estimate_tokens(text),
            reasoning=NOT_REPORTED,
            cache_read=0,
            cache_write=0,
            synthetic=True,
        )
        return Response(text=text, usage=usage, stop="end",
                        latency_s=time.perf_counter() - start, served_model=f"mock:{model.id}")
