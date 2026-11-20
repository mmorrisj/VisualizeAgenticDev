"""Checks a student can attach to their own test (spec section 10.3, step 1).

- expected: the answer must contain an expected value (case and spacing ignored);
- phrases:  every phrase must appear; the score is the share that do;
- command:  a shell command decides pass or fail by its exit code. It runs in a
  temporary directory holding the answer (answer.txt) and the attached files,
  with a scrubbed environment and a timeout. That contains mistakes but is not
  a security boundary, so the app refuses command checks unless the server
  turns them on (PROMPTLAB_ALLOW_COMMAND_CHECKS=1).
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .checks import CheckResult
from .sandbox import scrubbed_env

COMMAND_TIMEOUT = 30


class CustomCheck(BaseModel):
    kind: Literal["none", "expected", "phrases", "command"] = "none"
    expected: str = ""
    phrases: list[str] = Field(default_factory=list)
    command: str = ""

    @model_validator(mode="after")
    def _complete(self):
        if self.kind == "expected" and not self.expected.strip():
            raise ValueError("an expected-value check needs the expected value")
        if self.kind == "phrases" and not [p for p in self.phrases if p.strip()]:
            raise ValueError("a phrases check needs at least one phrase")
        if self.kind == "command" and not self.command.strip():
            raise ValueError("a command check needs a command")
        return self

    @property
    def active(self) -> bool:
        return self.kind != "none"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def run_check(check: CustomCheck, answer: str, files: dict[str, str]) -> CheckResult | None:
    """None when there is no check: the result is then labelled AI-judged only."""
    if check.kind == "none":
        return None
    if check.kind == "expected":
        found = _norm(check.expected) in _norm(answer)
        return CheckResult(1.0 if found else 0.0, {"expected": check.expected, "found": found})
    if check.kind == "phrases":
        phrases = [p for p in check.phrases if p.strip()]
        found = [p for p in phrases if _norm(p) in _norm(answer)]
        return CheckResult(round(len(found) / len(phrases), 4),
                           {"found": found, "missing": [p for p in phrases if p not in found]})
    with tempfile.TemporaryDirectory(prefix="promptlab-check-") as tmp:
        Path(tmp, "answer.txt").write_text(answer, encoding="utf-8")
        for name, text in files.items():
            Path(tmp, Path(name).name).write_text(text, encoding="utf-8")
        try:
            proc = subprocess.run(["bash", "-c", check.command], cwd=tmp, env=scrubbed_env(), capture_output=True,
                                  text=True, timeout=COMMAND_TIMEOUT)
        except subprocess.TimeoutExpired:
            return CheckResult(0.0, {"exit_code": None}, error=f"the command took longer than {COMMAND_TIMEOUT} s")
    output = (proc.stdout + proc.stderr)[-2000:]
    return CheckResult(1.0 if proc.returncode == 0 else 0.0, {"exit_code": proc.returncode, "output": output})
