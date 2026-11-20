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

For bring-your-own tests (part C) there is no task folder. The mock then
assesses a prompt by its length, drafts a fixed rubric, and answers well when
the model is high quality or the prompt has at least 25 words: a good answer
repeats the prompt's last line, so a test can put its expected value there.

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


TIERS = ("terse", "goal", "context", "spec")
CUSTOM_ROLES = {"assess", "rubric", "custom_answer"}


class MockBackend:
    def complete(self, request: Request, model: ModelConfig) -> Response:
        task_id = request.meta.get("task")
        role = request.meta.get("role", "answer")
        if role in CUSTOM_ROLES or (role == "judge" and not task_id):
            text = getattr(self, f"_custom_{role}")(request, model)
        else:
            if not task_id:
                raise BackendError("mock backend needs request.meta['task']")
            task = load_task(task_id)
            if role == "harness":
                from .mock_harness import respond  # scripted multi-request sessions
                return respond(task, request, model)
            text = getattr(self, f"_{role.replace('-', '_')}")(task, request, model)
        start = time.perf_counter()
        usage = Usage(input=estimate_tokens({"system": request.system, "messages": request.messages}),
                      output=estimate_tokens(text), reasoning=NOT_REPORTED, cache_read=0, cache_write=0,
                      synthetic=True)
        return Response(text=text, usage=usage, stop="end", latency_s=time.perf_counter() - start,
                        served_model=f"mock:{model.id}")

    # --- model under test ---------------------------------------------------
    def _answer(self, task, request, model):
        variant = request.meta.get("variant", "")
        good = model.mock_quality == "high" or variant in INFORMED_VARIANTS
        if variant == "own":  # a student's own prompt: judged by its length, like part C
            prompt = request.messages[0]["content"].split("\n\nFile: ", 1)[0]
            good = good or len(prompt.split()) >= 25
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


    # --- part C: bring your own test (no task folder) -------------------------------
    @staticmethod
    def _prompt_of(request: Request) -> str:
        content = request.messages[0]["content"]
        return content.split("<prompt>\n", 1)[1].split("\n</prompt>", 1)[0] if "<prompt>\n" in content else content

    def _custom_assess(self, request, model):
        prompt = self._prompt_of(request)
        words = len(prompt.split())
        tier = "terse" if words < 8 else "goal" if words < 25 else "context" if words < 60 else "spec"
        index = TIERS.index(tier)
        markers = sum(m in prompt.lower() for m in ("you are", "step", "format", "##", "\n- "))
        rewrites = [{"tier": t, "prompt": f"Write for the person who asked ({t} tier).\n\n{prompt}",
                     "invented": [{"id": f"{t}-1", "text": "Use British spelling throughout."}]}
                    for t in TIERS[index + 1:]]
        missing = [{"text": "Who will read the result, and what they need it for", "kind": "only-you-know"}]
        if "File:" in request.messages[0]["content"]:
            missing.append({"text": "What the attached file says about the details", "kind": "discoverable"})
        return json.dumps({"tier": tier, "technique": 1 + min(2, markers), "information": max(1, index),
                           "missing": missing, "rewrites": rewrites,
                           "recommended_tier": TIERS[min(index + 1, len(TIERS) - 1)]})

    def _custom_rubric(self, request, model):
        anchors = {"1": "misses the point", "3": "partly right", "5": "fully right"}
        return json.dumps({"criteria": [
            {"id": "correct", "name": "Correct", "description": "Does what was asked, accurately.", "anchors": anchors},
            {"id": "complete", "name": "Complete", "description": "Covers everything that was asked.", "anchors": anchors},
            {"id": "clear", "name": "Clear", "description": "Easy for the reader to use.", "anchors": anchors},
        ]})

    def _custom_custom_answer(self, request, model):
        prompt = request.messages[0]["content"].split("\n\nFile: ", 1)[0]
        if model.mock_quality == "high" or len(prompt.split()) >= 25:
            last = [line for line in prompt.strip().splitlines() if line.strip()][-1]
            return f"Here is what you asked for.\n\n{last}\n"
        return "I am not sure what you need. Could you say more?\n"

    def _custom_judge(self, request, model):
        content = request.messages[0]["content"]
        answer = content.split("<answer>\n", 1)[1].rsplit("\n</answer>", 1)[0]
        base = 4 if answer.startswith("Here is") else 2
        if model.id.endswith("-2"):
            base = max(1, base - 1)
        return json.dumps({"criteria": [{"id": cid, "score": base, "quote": _snippet(answer), "reason": "mock judgement"}
                                        for cid in request.meta["rubric_ids"]]})
