"""Shared helpers for task checks (spec section 7.1: checks with known answers come first).

A check returns a CheckResult: a score from 0 to 1, whether it fully passed, and
details explaining every sub-check, so a score can always be traced.
"""

from __future__ import annotations

import ast
import difflib
import sys
from dataclasses import asdict, dataclass, field


@dataclass
class CheckResult:
    score: float
    details: dict = field(default_factory=dict)
    artifact: str = ""          # what was extracted from the answer and checked
    error: str = ""             # set when the answer could not be checked at all

    @property
    def passed(self) -> bool:
        return self.score >= 0.999

    def to_dict(self) -> dict:
        data = asdict(self)
        data["passed"] = self.passed
        return data


def combine(parts: dict[str, float], weights: dict[str, float]) -> float:
    """Weighted mean of sub-scores in [0, 1]; every weighted part must be present."""
    missing = set(weights) - set(parts)
    if missing:
        raise ValueError(f"missing sub-scores: {sorted(missing)}")
    total = sum(weights.values())
    return round(sum(parts[k] * w for k, w in weights.items()) / total, 4)


def parse_python(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def public_signatures(tree: ast.Module) -> dict[str, tuple]:
    """Top-level public functions: name -> (positional names, keyword-only names,
    number of positional defaults, has *args, has **kwargs)."""
    sigs = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            a = node.args
            sigs[node.name] = (
                tuple(x.arg for x in a.posonlyargs + a.args),
                tuple(x.arg for x in a.kwonlyargs),
                len(a.defaults),
                a.vararg is not None,
                a.kwarg is not None,
            )
    return sigs


def signature_changes(original: ast.Module, candidate: ast.Module) -> list[str]:
    """Public functions that were removed or whose signature changed."""
    before, after = public_signatures(original), public_signatures(candidate)
    problems = []
    for name, sig in before.items():
        if name not in after:
            problems.append(f"{name}: removed")
        elif after[name] != sig:
            problems.append(f"{name}: signature changed")
    return problems


def non_stdlib_imports(tree: ast.Module, local: set[str] = frozenset()) -> list[str]:
    """Top-level module names imported that are neither standard library nor `local`
    (the task's own modules, such as the module under test)."""
    stdlib = set(sys.stdlib_module_names) | {"__future__"} | set(local)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return sorted(found - stdlib)


def changed_lines(before: str, after: str) -> int:
    """Lines added plus lines removed: the size of the diff a reviewer would read."""
    diff = difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
    return sum(1 for line in diff if line[:1] in "+-" and not line.startswith(("+++", "---")))
