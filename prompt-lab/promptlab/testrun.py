"""Run a test file and print one JSON line of results. Standard library only.

Invoked in a subprocess by sandbox.run_tests, never imported by the engine:

    python -I testrun.py <workdir> <test_file>

Collects plain `test_*` functions and unittest.TestCase classes, so model-written
tests need neither pytest nor any other dependency. Each test runs in isolation:
one failing test never stops the rest.
"""

import importlib.util
import json
import sys
import traceback
import unittest


def main() -> int:
    workdir, test_file = sys.argv[1], sys.argv[2]
    sys.path.insert(0, workdir)
    results = {"passed": 0, "failed": 0, "errors": 0, "tests": []}
    try:
        spec = importlib.util.spec_from_file_location("model_tests", test_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except BaseException:  # noqa: BLE001 - report import failures as data
        results["import_error"] = traceback.format_exc(limit=3)[-800:]
        print(json.dumps(results))
        return 0

    def record(name, outcome, detail=""):
        results[outcome] += 1
        results["tests"].append({"name": name, "outcome": outcome, "detail": detail[-300:]})

    for name, obj in sorted(vars(module).items()):
        if name.startswith("test") and callable(obj) and not isinstance(obj, type):
            try:
                obj()
                record(name, "passed")
            except AssertionError as err:
                record(name, "failed", repr(err))
            except BaseException:  # noqa: BLE001
                record(name, "errors", traceback.format_exc(limit=2))
        elif isinstance(obj, type) and issubclass(obj, unittest.TestCase) and obj is not unittest.TestCase:
            suite = unittest.defaultTestLoader.loadTestsFromTestCase(obj)
            for case in suite:
                outcome = unittest.TestResult()
                case.run(outcome)
                if outcome.errors:
                    record(case.id(), "errors", outcome.errors[0][1])
                elif outcome.failures:
                    record(case.id(), "failed", outcome.failures[0][1])
                else:
                    record(case.id(), "passed")
    print(json.dumps(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
