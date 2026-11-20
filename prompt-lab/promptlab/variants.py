"""Generate the AI-assisted prompt variants (spec section 5.1).

Run once per task with the primary judge model; the results are stored in the
task's prompts/ folder and every model in the study sees the same text.

- ai-expanded:    the terse prompt, rewritten by the model "into a detailed prompt".
- ai-interviewed: the model asks the questions it needs answered; a simulated
                  requester answers from the task's facts (and only those); the
                  model then writes the prompt.

For both, the model then lists every requirement in the new prompt that is not
among the task's facts. These invented requirements are counted for prediction
P4 after an instructor confirms the list (set `confirmed_by_instructor: true`).

Spec note: the spec says interview answers come from "a fixed script per task".
Questions are not known in advance, so the requester instead answers from the
task's fixed fact list; the whole exchange is stored, so the study stays
reproducible.
"""

from __future__ import annotations

from datetime import date

import yaml
from pydantic import BaseModel, Field

from .config import ModelConfig
from .llm import ask, ask_json
from .tasks import Task

GENERATED = ("ai-expanded", "ai-interviewed")

WRITER_SYSTEM = "You write prompts that another AI model will follow."


class Questions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=8)


class Answers(BaseModel):
    answers: list[str]


class InventedItem(BaseModel):
    text: str
    quote: str


class Invented(BaseModel):
    invented: list[InventedItem]


def _files_block(task: Task) -> str:
    return "\n\n".join(f"File: {name}\n```\n{task.read('input', name).rstrip()}\n```"
                       for name in task.spec.context_files)


def _facts_block(task: Task) -> str:
    return "\n".join(f"- {f.text}" for f in task.spec.facts)


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```") and text.endswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return text.strip() + "\n"


def invented_requirements(task: Task, prompt: str, model: ModelConfig) -> dict:
    """Requirements in `prompt` that the task's facts do not support, each with a quote."""
    user = (f"Original request: {task.prompt('terse')}\n\n"
            f"What the requester actually wants (the complete list):\n{_facts_block(task)}\n\n"
            f"A prompt someone wrote for this request:\n<prompt>\n{prompt}\n</prompt>\n\n"
            "List every requirement or instruction in the prompt that is neither in the list above nor a "
            "restatement of the original request. For each, give a short description and an exact quote "
            "from the prompt. Formatting instructions count. If there are none, return an empty list.\n"
            'Reply with JSON only: {"invented": [{"text": "...", "quote": "..."}]}')

    def quotes_present(value: Invented) -> str:
        missing = [i.quote for i in value.invented if i.quote.strip() not in prompt]
        return f"these quotes are not in the prompt: {missing}" if missing else ""

    result = ask_json(model, "You compare a prompt with what its author actually wanted.", user, Invented,
                      meta={"role": "invented", "task": task.id}, extra_check=quotes_present)
    return {
        "items": [i.model_dump() for i in result.value.invented] if result.value else [],
        "error": result.error,
        "confirmed_by_instructor": False,
    }


def generate_expanded(task: Task, model: ModelConfig) -> dict:
    user = (f"Rewrite this request into a detailed prompt for an AI model. The files below will be attached "
            f"to the prompt.\n\nRequest: {task.prompt('terse')}\n\n{_files_block(task)}\n\n"
            "Reply with only the new prompt, without the files.")
    response = ask(model, WRITER_SYSTEM, user, meta={"role": "expand", "task": task.id})
    prompt = _strip_fences(response.text)
    return {"prompt": prompt, "transcript": [{"writer": response.text}],
            "invented": invented_requirements(task, prompt, model)}


def generate_interviewed(task: Task, model: ModelConfig) -> dict:
    asked = ask_json(model, WRITER_SYSTEM,
                     f"Someone made this request: {task.prompt('terse')}\n\n{_files_block(task)}\n\n"
                     "Before writing a detailed prompt for it, list the questions you need the requester to "
                     "answer (at most 8).\n"
                     'Reply with JSON only: {"questions": ["..."]}',
                     Questions, meta={"role": "interview-questions", "task": task.id})
    if asked.value is None:
        raise RuntimeError(f"{task.id}: no usable questions: {asked.error}")
    questions = asked.value.questions
    numbered = "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1))
    answered = ask_json(model, "You play the person who made a request. You answer only from what you know.",
                        f"You asked for: {task.prompt('terse')}\n\nWhat you know and want:\n{_facts_block(task)}\n\n"
                        f"Answer each question using only what you know. If it does not cover a question, "
                        f"answer \"No preference.\"\n\nQuestions:\n{numbered}\n\n"
                        'Reply with JSON only: {"answers": ["...", "..."]} with one answer per question, in order.',
                        Answers, meta={"role": "interview-answers", "task": task.id},
                        extra_check=lambda v: "" if len(v.answers) == len(questions)
                        else f"expected {len(questions)} answers, got {len(v.answers)}")
    if answered.value is None:
        raise RuntimeError(f"{task.id}: no usable answers: {answered.error}")
    qa = [{"question": q, "answer": a} for q, a in zip(questions, answered.value.answers)]
    qa_block = "\n".join(f"Q: {p['question']}\nA: {p['answer']}" for p in qa)
    response = ask(model, WRITER_SYSTEM,
                   f"Request: {task.prompt('terse')}\n\nThe requester answered your questions:\n{qa_block}\n\n"
                   f"{_files_block(task)}\n\nWrite a detailed prompt for an AI model that will get this request "
                   "and the files above. Reply with only the new prompt, without the files.",
                   meta={"role": "interview-prompt", "task": task.id})
    prompt = _strip_fences(response.text)
    return {"prompt": prompt, "transcript": qa, "invented": invented_requirements(task, prompt, model)}


def generate(task: Task, model: ModelConfig, which: tuple[str, ...] = GENERATED) -> list[str]:
    """Generate and store the variants; returns the files written."""
    written = []
    for variant in which:
        result = generate_expanded(task, model) if variant == "ai-expanded" else generate_interviewed(task, model)
        task.path("prompts", f"{variant}.md").write_text(result["prompt"], encoding="utf-8")
        meta = {"variant": variant, "generated_by": model.id, "gateway_id": model.gateway_id,
                "date": date.today().isoformat(), "transcript": result["transcript"],
                "invented_requirements": result["invented"]}
        meta_path = task.path("prompts", f"{variant}.meta.yaml")
        meta_path.write_text(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True), encoding="utf-8")
        written += [f"prompts/{variant}.md", f"prompts/{variant}.meta.yaml"]
    return written


def invented_count(task: Task, variant: str) -> int | None:
    """Confirmed invented requirements for a generated variant; None until an instructor confirms."""
    path = task.path("prompts", f"{variant}.meta.yaml")
    if not path.is_file():
        return None
    meta = yaml.safe_load(path.read_text(encoding="utf-8"))
    invented = meta.get("invented_requirements") or {}
    return len(invented.get("items", [])) if invented.get("confirmed_by_instructor") else None
