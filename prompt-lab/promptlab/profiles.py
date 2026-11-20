"""Run profiles (spec section 10): which tasks, variants, models, repeats, and judges a part uses."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from . import CONFIG_DIR
from .config import ModelConfig
from .tasks import task_ids


class JudgeSettings(BaseModel):
    primary: str
    cross_check: str | None = None
    cross_check_share: float = Field(default=0.2, ge=0, le=1)


class HarnessSettings(BaseModel):
    """Harness sessions in a profile (spec sections 5.2 and 6.2). Models default to the profile's."""

    tasks: list[str] | Literal["all"] = "all"
    variants: list[str] = ["h-terse", "h-discoverable-gap", "h-private-gap", "h-full"]
    models: list[str] | None = None
    repeats: int = Field(default=1, ge=1)
    max_requests: int = Field(default=25, ge=1)
    max_input_tokens: int = Field(default=60_000, ge=1)


class Profile(BaseModel):
    name: str
    tasks: list[str] | Literal["all"] = "all"
    variants: list[str] = []
    models: list[str]
    repeats: int = Field(default=1, ge=1)
    judge: JudgeSettings | None = None
    harness: HarnessSettings | None = None

    def task_list(self) -> list[str]:
        return task_ids() if self.tasks == "all" else list(self.tasks)

    def harness_tasks(self) -> list[str]:
        if not self.harness:
            return []
        return task_ids() if self.harness.tasks == "all" else list(self.harness.tasks)

    def harness_models(self) -> list[str]:
        if not self.harness:
            return []
        return list(self.harness.models) if self.harness.models is not None else list(self.models)

    def check_models(self, models: dict[str, ModelConfig]) -> None:
        named = list(self.models) + self.harness_models()
        if self.judge:
            named += [self.judge.primary] + ([self.judge.cross_check] if self.judge.cross_check else [])
        unknown = sorted(set(named) - set(models))
        if unknown:
            raise ValueError(f"profile {self.name} names unknown models: {unknown}")


def load_profile(name_or_path: str) -> Profile:
    path = Path(name_or_path)
    if not path.suffix:
        path = CONFIG_DIR / f"{name_or_path}.yaml"
    return Profile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
