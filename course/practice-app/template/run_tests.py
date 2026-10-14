"""Minimal test runner (standard library only) for environments without pytest.

Runs every function named test_* in tests/test_*.py and prints a pytest-style
summary. Exit code is 0 when all tests pass, 1 otherwise.

Usage: python3 run_tests.py [-q]
"""
import importlib.util
import pathlib
import sys
import traceback

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def load(path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    quiet = "-q" in sys.argv
    passed, failed = 0, []
    for path in sorted((ROOT / "tests").glob("test_*.py")):
        module = load(path)
        for name in sorted(n for n in dir(module) if n.startswith("test_")):
            func = getattr(module, name)
            if not callable(func):
                continue
            try:
                func()
                passed += 1
                if not quiet:
                    print(f"PASS  {path.name}::{name}")
            except Exception:  # noqa: BLE001 - report every failure type
                failed.append((f"{path.name}::{name}", traceback.format_exc(limit=2)))
                print(f"FAIL  {path.name}::{name}")
    for test_id, tb in failed:
        print(f"\n--- {test_id} ---\n{tb}")
    summary = f"{len(failed)} failed, {passed} passed" if failed else f"{passed} passed"
    print(summary)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
