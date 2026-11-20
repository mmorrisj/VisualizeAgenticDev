"""Checks for write-tests: pass on the correct code, then catch as many planted bugs as possible."""

from promptlab.checks import CheckResult, combine, non_stdlib_imports, parse_python
from promptlab.extract import extract
from promptlab.sandbox import run_tests


def _ran(result: dict) -> int:
    return result["passed"] + result["failed"] + result["errors"]


def check(answer: str, task) -> CheckResult:
    tests = extract(answer, "python")
    tree = parse_python(tests)
    if tree is None:
        return CheckResult(0.0, {"parses": False}, tests, "the tests do not parse")
    third_party = non_stdlib_imports(tree, local={"business_days"})
    if third_party:
        return CheckResult(0.0, {"non_stdlib_imports": third_party}, tests,
                           "imports outside the standard library: " + ", ".join(third_party))

    correct = run_tests({"business_days.py": task.read("input", "business_days.py")}, tests)
    details = {"tests_found": _ran(correct), "on_correct_code": f"{correct['passed']}/{_ran(correct)}"}
    if _ran(correct) == 0:
        return CheckResult(0.0, details, tests, correct.get("import_error") or "no tests found")
    if correct["passed"] != _ran(correct):
        details["failing_on_correct"] = [t["name"] for t in correct["tests"] if t["outcome"] != "passed"]
        return CheckResult(0.0, details, tests, "some tests fail on the correct code")

    caught, missed = [], []
    for mutant in sorted(task.path("hidden", "mutants").glob("*.py")):
        result = run_tests({"business_days.py": mutant.read_text(encoding="utf-8")}, tests)
        killed = result.get("timeout") or result.get("crash") or result["passed"] < _ran(result) or _ran(result) == 0
        (caught if killed else missed).append(mutant.stem)
    total = len(caught) + len(missed)
    details.update(caught=caught, missed=missed, mutants=f"{len(caught)}/{total}")
    return CheckResult(combine({"mutants_caught": len(caught) / total}, task.spec.weights), details, tests)
