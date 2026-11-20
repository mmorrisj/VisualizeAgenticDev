"""Tasks (spec section 4): inputs, the facts a good answer needs, prompts, and checks.

Each task is a folder under tasks/:

    task.yaml       id, title, artifact kind, which files go into the prompt, facts
    input/          files given to the model (and to the checks)
    hidden/         files the checks use but the model never sees
    prompts/        one file per prompt variant
    answers/        known-good and known-bad answers (self-test and mock backend)
    checks.py       check(answer_text, task) -> CheckResult
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel

from . import TASKS_DIR


class Fact(BaseModel):
    id: str
    text: str
    kind: Literal["discoverable", "private"]   # private = only the user knows it


class TaskSpec(BaseModel):
    id: str
    title: str
    artifact: Literal["python", "sql", "tests", "text"]
    context_files: list[str] = []      # files under input/ placed in the one-shot prompt
    facts: list[Fact]
    weights: dict[str, float] = {}     # how sub-checks combine into the score
    notes: str = ""


class Task:
    def __init__(self, folder: Path):
        self.dir = folder
        self.spec = TaskSpec.model_validate(yaml.safe_load((folder / "task.yaml").read_text(encoding="utf-8")))
        self._checks = None

    @property
    def id(self) -> str:
        return self.spec.id

    def path(self, *parts: str) -> Path:
        return self.dir.joinpath(*parts)

    def read(self, *parts: str) -> str:
        return self.path(*parts).read_text(encoding="utf-8")

    def variants(self) -> list[str]:
        return sorted(p.stem for p in self.path("prompts").glob("*.md"))

    def prompt(self, variant: str) -> str:
        path = self.path("prompts", f"{variant}.md")
        if not path.is_file():
            raise KeyError(f"task {self.id} has no prompt variant '{variant}' (have: {self.variants()})")
        return path.read_text(encoding="utf-8").strip()

    def answer(self, name: str) -> str:
        return self.read("answers", f"{name}.md")

    def answers(self) -> list[str]:
        return sorted(p.stem for p in self.path("answers").glob("*.md"))

    def build_user_message(self, variant: str) -> str:
        """The prompt, then each context file in a labelled fence. The prompt is the only
        thing that changes between variants; the attached files are identical."""
        parts = [self.prompt(variant)]
        for name in self.spec.context_files:
            fence = "sql" if name.endswith(".sql") else "python" if name.endswith(".py") else ""
            parts.append(f"File: {name}\n```{fence}\n{self.read('input', name).rstrip()}\n```")
        return "\n\n".join(parts)

    def check(self, answer_text: str):
        if self._checks is None:
            spec = importlib.util.spec_from_file_location(f"promptlab_task_{self.id.replace('-', '_')}",
                                                          self.path("checks.py"))
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._checks = module
        return self._checks.check(answer_text, self)


@lru_cache(maxsize=None)
def load_task(task_id: str) -> Task:
    folder = TASKS_DIR / task_id
    if not (folder / "task.yaml").is_file():
        raise KeyError(f"unknown task '{task_id}' (have: {task_ids()})")
    return Task(folder)


def task_ids() -> list[str]:
    return sorted(p.parent.name for p in TASKS_DIR.glob("*/task.yaml"))
