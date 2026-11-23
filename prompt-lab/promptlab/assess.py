"""Prompt assessment and rubric drafting for part C, bring your own test (spec section 10.3).

The primary judge model reads a student's prompt (and any attached file) and returns:

- a tier: terse, goal, context or spec, which is how much the prompt states;
- a technique score and an information score, each 1 to 3 (the section 5.1 grid);
- the missing information, each item classed as discoverable (in the files) or
  only-you-know;
- rewrites at the tiers above the student's. Every requirement the AI made up is
  kept in a separate `invented` list instead of blended into the prompt text, so
  the student can see it, disagree with it, and delete it before anything runs.

It also drafts a rubric from the prompt's intent, which the student approves or
edits before any result exists.

Both use the lab's JSON helper: plain JSON requested in the prompt, validated
here, with one retry.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .config import ModelConfig
from .llm import ask_json

Tier = Literal["terse", "goal", "context", "spec"]
TIERS: tuple[str, ...] = ("terse", "goal", "context", "spec")

TIER_MEANING = {
    "terse": "the bare intent in a few words",
    "goal": "the intent and what the result is for",
    "context": "the goal plus the important context and constraints",
    "spec": "everything a careful colleague would need, including acceptance criteria",
}


class MissingItem(BaseModel):
    text: str
    kind: Literal["discoverable", "only-you-know"]


class Invented(BaseModel):
    id: str
    text: str


class Rewrite(BaseModel):
    tier: Tier
    prompt: str                          # the rewrite without anything the AI made up
    invented: list[Invented] = []        # what the AI made up, kept apart

    def compose(self, keep: set[str] | None = None) -> str:
        """The prompt that runs: the rewrite plus the invented requirements the student kept."""
        kept = [i.text for i in self.invented if keep is None or i.id in keep]
        if not kept:
            return self.prompt.strip()
        return self.prompt.strip() + "\n\n" + "\n".join(f"- {text}" for text in kept)


class Assessment(BaseModel):
    tier: Tier
    technique: int = Field(ge=1, le=3)
    information: int = Field(ge=1, le=3)
    missing: list[MissingItem] = []
    rewrites: list[Rewrite] = []
    recommended_tier: Tier

    def rewrite(self, tier: str) -> Rewrite | None:
        return next((r for r in self.rewrites if r.tier == tier), None)


class Criterion(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9-]{1,32}$")
    name: str
    description: str
    anchors: dict[Literal["1", "3", "5"], str]


class Rubric(BaseModel):
    criteria: list[Criterion] = Field(min_length=3, max_length=5)


ASSESS_SYSTEM = ("You review prompts that people write for AI models. You are direct and specific. "
                 "You never pass off your own assumptions as the requester's requirements.")

RUBRIC_SYSTEM = "You write grading rubrics. Each criterion must be checkable against an answer."


def _files_block(files: dict[str, str]) -> str:
    if not files:
        return "(no files attached)"
    return "\n\n".join(f"File: {name}\n```\n{text.rstrip()}\n```" for name, text in files.items())


def assessment_prompt(prompt: str, files: dict[str, str]) -> str:
    tiers = "\n".join(f"- {t}: {TIER_MEANING[t]}" for t in TIERS)
    return (
        f"A person wrote this prompt for an AI model:\n<prompt>\n{prompt}\n</prompt>\n\n"
        f"Files attached to it:\n{_files_block(files)}\n\n"
        f"Classify how much the prompt states, as one tier:\n{tiers}\n\n"
        "Score technique (role, structure, steps, output format) and information (facts and constraints "
        "the task needs) from 1 to 3 each.\n"
        "List the information that is missing. Class each item as \"discoverable\" if the attached files "
        "contain it, or \"only-you-know\" if only the requester could say it.\n"
        "Write one rewrite for each tier above the prompt's tier. In a rewrite, use only what the requester "
        "said or the files show. Anything you would add from your own assumptions goes in that rewrite's "
        "\"invented\" list, one item each with a short id, and must not appear in the rewrite's prompt text.\n"
        "Say which tier you recommend for this task.\n\n"
        "Reply with JSON only, in this shape: "
        '{"tier": "goal", "technique": 1, "information": 2, '
        '"missing": [{"text": "...", "kind": "only-you-know"}], '
        '"rewrites": [{"tier": "context", "prompt": "...", "invented": [{"id": "i1", "text": "..."}]}], '
        '"recommended_tier": "context"}'
    )


def _check_assessment(value: Assessment) -> str:
    above = list(TIERS[TIERS.index(value.tier) + 1:])
    got = [r.tier for r in value.rewrites]
    if got != above:
        return f"give exactly one rewrite for each tier above {value.tier}, in order: {above} (got {got})"
    if TIERS.index(value.recommended_tier) < TIERS.index(value.tier):
        return "the recommended tier cannot be below the prompt's own tier"
    for rewrite in value.rewrites:
        ids = [i.id for i in rewrite.invented]
        if len(set(ids)) != len(ids):
            return f"invented ids must be unique within the {rewrite.tier} rewrite"
        blended = [i.id for i in rewrite.invented if i.text.strip() and i.text.strip() in rewrite.prompt]
        if blended:
            return f"invented items {blended} also appear in the {rewrite.tier} prompt text; keep them only in the list"
    return ""


def assess_prompt(prompt: str, files: dict[str, str], model: ModelConfig) -> tuple[Assessment | None, dict]:
    """(assessment or None, a record of the call: model, attempts, tokens, error)."""
    result = ask_json(model, ASSESS_SYSTEM, assessment_prompt(prompt, files), Assessment,
                      meta={"role": "assess"}, extra_check=_check_assessment)
    return result.value, _record(model, result)


def rubric_prompt(prompt: str, files: dict[str, str]) -> str:
    return (
        f"A person will use this prompt with several AI models:\n<prompt>\n{prompt}\n</prompt>\n\n"
        f"Files attached to it:\n{_files_block(files)}\n\n"
        "Draft a rubric of 3 to 5 criteria for grading the answers, from what the person wants. "
        "Each criterion has a short lowercase id (letters, digits, hyphens), a name, a one-sentence "
        "description, and anchors describing a score of 1, 3 and 5.\n\n"
        'Reply with JSON only, in this shape: {"criteria": [{"id": "correct", "name": "...", '
        '"description": "...", "anchors": {"1": "...", "3": "...", "5": "..."}}]}'
    )


def _check_rubric(value: Rubric) -> str:
    ids = [c.id for c in value.criteria]
    return "criterion ids must be unique" if len(set(ids)) != len(ids) else ""


def draft_rubric(prompt: str, files: dict[str, str], model: ModelConfig) -> tuple[Rubric | None, dict]:
    result = ask_json(model, RUBRIC_SYSTEM, rubric_prompt(prompt, files), Rubric,
                      meta={"role": "rubric"}, extra_check=_check_rubric)
    return result.value, _record(model, result)


def _record(model: ModelConfig, result) -> dict:
    return {"model": model.id, "attempts": len(result.responses),
            "tokens": [r.usage.to_dict() for r in result.responses], "error": result.error}
