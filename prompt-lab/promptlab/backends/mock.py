"""Deterministic mock backend, for engine tests and development without a model.

As a model under test it answers from each task's prepared answers
(tasks/<task>/answers/). A model's `mock_quality` decides which answer it gives:

- high: the good answer for every prompt variant;
- low:  the bad answer for terse prompts, the good answer once the prompt is
        informed. This mimics the pattern the study looks for, but it is a
        script, not evidence: results from mock models are labelled synthetic.

It also plays the lab's other roles (request.meta["role"]): the prompt writer,
the simulated requester, the invented-requirements check, and the judge. The
mock judge scores from the run's check score, which only the mock can see.

Token counts use the course estimator and are marked synthetic.
"""

from __future__ import annotations

import json
import time

import yaml

from ..config import ModelConfig
from ..tasks import load_task
from ..tokens import NOT_REPORTED, Usage, estimate_tokens
from .base import BackendError, Request, Response

INFORMED_VARIANTS = {"informed", "full", "ai-interviewed"}
INVENTED_LINE = "- Add type hints and a docstring to every function you write."


def _snippet(text: str) -> str:
    """A short exact substring of text, for evidence quotes."""
    for line in text.splitlines():
        line = line.strip().strip("`*#>- ")
        if len(line) >= 12:
            return line[:60]
    return "(absent)"


class MockBackend:
    def complete(self, request: Request, model: ModelConfig) -> Response:
        task_id = request.meta.get("task")
        if not task_id:
            raise BackendError("mock backend needs request.meta['task']")
        task = load_task(task_id)
        role = request.meta.get("role", "answer")
        text = getattr(self, f"_{role.replace('-', '_')}")(task, request, model)
        start = time.perf_counter()
        usage = Usage(input=estimate_tokens({"system": request.system, "messages": request.messages}),
                      output=estimate_tokens(text), reasoning=NOT_REPORTED, cache_read=0, cache_write=0,
                      synthetic=True)
        return Response(text=text, usage=usage, stop="end", latency_s=time.perf_counter() - start,
                        served_model=f"mock:{model.id}")

    # --- model under test ---------------------------------------------------
    def _answer(self, task, request, model):
        good = model.mock_quality == "high" or request.meta.get("variant", "") in INFORMED_VARIANTS
        kind = "good" if good else "bad"
        names = [n for n in task.answers() if n.startswith(kind)]
        if not names:
            raise BackendError(f"task {task.id} has no '{kind}' answer for the mock backend")
        return task.answer(names[0])

    # --- prompt writer and simulated requester ----------------------------------
    def _expand(self, task, request, model):
        return task.prompt("informed") + "\n" + INVENTED_LINE + "\n"

    def _interview_questions(self, task, request, model):
        return json.dumps({"questions": ["Who will use the result?", "Are there constraints I should know about?"]})

    def _interview_answers(self, task, request, model):
        facts = [f.text for f in task.spec.facts]
        return json.dumps({"answers": [facts[0], "; ".join(facts[1:])]})

    def _interview_prompt(self, task, request, model):
        return task.prompt("informed") + "\n"

    def _invented(self, task, request, model):
        prompt = request.messages[0]["content"]
        found = INVENTED_LINE in prompt.split("<prompt>", 1)[-1]
        items = [{"text": "type hints and docstrings were not requested", "quote": INVENTED_LINE}] if found else []
        return json.dumps({"invented": items})

    # --- judge ------------------------------------------------------------------
    def _judge(self, task, request, model):
        content = request.messages[0]["content"]
        answer = content.split("<answer>\n", 1)[1].rsplit("\n</answer>", 1)[0]
        check = request.meta.get("check_score")
        base = 3 if check is None else 1 + round(4 * check)
        if model.id.endswith("-2"):  # the cross-check judge is slightly harsher, so agreement is not trivial
            base = max(1, base - 1)
        rubric = yaml.safe_load(task.read("rubric.yaml"))
        out = {"criteria": [{"id": c["id"], "score": base, "quote": _snippet(answer),
                             "reason": "mock judgement"} for c in rubric["criteria"]]}
        if rubric.get("claims"):
            source = task.read("input", task.spec.context_files[0])
            out["claims"] = [{"claim": "the report's first line", "supported": True, "source_quote": _snippet(source)}]
        return json.dumps(out)
