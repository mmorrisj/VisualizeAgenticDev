"""The AI judge (spec section 7.2).

- Blind: the judge sees what the requester wanted, the attached files, and the
  answer. It never sees the model name or the prompt variant.
- One rubric per task (tasks/<task>/rubric.yaml), 1 to 5 per criterion.
- Evidence required: every score quotes the answer; a quote that is not in the
  answer is rejected and the judge is asked once more. Criteria still missing
  after that are recorded as missing, never guessed.
- For summaries, the judge also lists the factual claims and quotes the report
  for each one it calls supported; those quotes are verified the same way.

The judge's own token usage is recorded with each judgement.
"""

from __future__ import annotations

import re

import yaml
from pydantic import BaseModel, Field

from .config import ModelConfig
from .llm import ask_json
from .tasks import Task

ABSENT = "(absent)"  # quote used when the point is that something is missing from the answer

SYSTEM = ("You grade answers to tasks. You do not know who or what wrote the answer, and it does not matter. "
          "Judge only against the rubric and quote the answer for every score.")


class CriterionScore(BaseModel):
    id: str
    score: int = Field(ge=1, le=5)
    quote: str
    reason: str


class Claim(BaseModel):
    claim: str
    supported: bool
    source_quote: str = ""


class Judgement(BaseModel):
    criteria: list[CriterionScore]
    claims: list[Claim] | None = None


def normalize(text: str) -> str:
    """Compare quotes loosely: ignore Markdown emphasis, code ticks, case, and spacing."""
    return re.sub(r"\s+", " ", re.sub(r"[*_`#>]", "", text)).strip().lower()


def load_rubric(task: Task) -> dict:
    return yaml.safe_load(task.read("rubric.yaml"))


def _rubric_block(rubric: dict) -> str:
    lines = []
    for c in rubric["criteria"]:
        anchors = "; ".join(f"{k}: {v}" for k, v in sorted(c["anchors"].items()))
        lines.append(f'- id "{c["id"]}" ({c["name"]}): {c["description"]} Anchors: {anchors}')
    return "\n".join(lines)


def build_prompt(task: Task, answer: str, rubric: dict) -> str:
    files = "\n\n".join(f"File: {n}\n```\n{task.read('input', n).rstrip()}\n```" for n in task.spec.context_files)
    claims = (
        '\nAlso list every factual claim in the answer as "claims": for each, say whether the files support it, '
        'and for supported claims give "source_quote", an exact quote from the files.\n' if rubric.get("claims") else "")
    shape = ('{"criteria": [{"id": "...", "score": 1, "quote": "...", "reason": "..."}]'
             + (', "claims": [{"claim": "...", "supported": true, "source_quote": "..."}]' if rubric.get("claims") else "")
             + "}")
    return (
        f"What the requester wanted:\n<request>\n{task.prompt('informed')}\n</request>\n\n"
        f"Files the requester attached:\n{files}\n\n"
        f"The answer to grade:\n<answer>\n{answer}\n</answer>\n\n"
        f"Rubric (score each criterion from 1 to 5):\n{_rubric_block(rubric)}\n\n"
        f'For each criterion give the score, a short exact quote from the answer as evidence (or "{ABSENT}" if the '
        "evidence is that something is missing), and a one-sentence reason.\n"
        f"{claims}\nReply with JSON only, in this shape: {shape}"
    )


def _verifier(task: Task, answer: str, rubric: dict):
    wanted = [c["id"] for c in rubric["criteria"]]
    answer_n = normalize(answer)
    sources_n = normalize("\n".join(task.read("input", n) for n in task.spec.context_files))

    def check(value: Judgement) -> str:
        got = [c.id for c in value.criteria]
        if sorted(got) != sorted(wanted):
            return f"criteria must be exactly {wanted}, got {got}"
        bad = [c.id for c in value.criteria if c.quote != ABSENT and normalize(c.quote) not in answer_n]
        if bad:
            return f"the quotes for {bad} are not in the answer; quote the answer exactly"
        if rubric.get("claims"):
            if value.claims is None:
                return "the claims list is missing"
            unsourced = [c.claim for c in value.claims if c.supported and normalize(c.source_quote) not in sources_n]
            if unsourced:
                return f"supported claims need an exact quote from the files: {unsourced[:3]}"
        return ""

    return check


def judge(task: Task, answer: str, model: ModelConfig, meta: dict | None = None) -> dict:
    """Score one answer. Returns a JSON-ready dict; `score` is in [0, 1] or None if judging failed."""
    rubric = load_rubric(task)
    result = ask_json(model, SYSTEM, build_prompt(task, answer, rubric), Judgement,
                      meta={"role": "judge", "task": task.id, **(meta or {})},
                      extra_check=_verifier(task, answer, rubric))
    out = {
        "judge": model.id,
        "attempts": len(result.responses),
        "tokens": [r.usage.to_dict() for r in result.responses],
        "error": result.error,
        "score": None,
        "criteria": [],
    }
    if result.value is None:
        return out
    out["criteria"] = [c.model_dump() for c in result.value.criteria]
    out["score"] = round(sum((c.score - 1) / 4 for c in result.value.criteria) / len(result.value.criteria), 4)
    if result.value.claims is not None:
        out["claims"] = [c.model_dump() for c in result.value.claims]
        out["unsupported_claims"] = sum(not c.supported for c in result.value.claims)
    return out
