"""Checks for refactor: hidden tests, public signatures, standard library only, actually changed."""

import ast

from promptlab.checks import (CheckResult, changed_lines, combine, non_stdlib_imports, parse_python,
                              signature_changes)
from promptlab.extract import extract
from promptlab.sandbox import run_tests

MIN_CHANGED_LINES = 10


def check(answer: str, task) -> CheckResult:
    original = task.read("input", "billing.py")
    code = extract(answer, "python")
    tree = parse_python(code)
    if tree is None:
        return CheckResult(0.0, {"parses": False}, code, "the returned module does not parse")

    tests = run_tests({"billing.py": code}, task.read("hidden", "test_billing.py"))
    total = tests["passed"] + tests["failed"] + tests["errors"]
    sig_problems = signature_changes(ast.parse(original), tree)
    third_party = non_stdlib_imports(tree)
    diff = changed_lines(original, code)
    parts = {
        "hidden_tests": tests["passed"] / total if total else 0.0,
        "signatures": 0.0 if sig_problems else 1.0,
        "stdlib_only": 0.0 if third_party else 1.0,
        "changed": 1.0 if diff >= MIN_CHANGED_LINES else 0.0,
    }
    details = {
        "parts": parts,
        "hidden_tests": f"{tests['passed']}/{total}",
        "failing_tests": [t["name"] for t in tests.get("tests", []) if t["outcome"] != "passed"],
        "signature_problems": sig_problems,
        "non_stdlib_imports": third_party,
        "changed_lines": diff,
    }
    for key in ("import_error", "timeout", "crash"):
        if key in tests:
            details[key] = tests[key]
    return CheckResult(combine(parts, task.spec.weights), details, code)
