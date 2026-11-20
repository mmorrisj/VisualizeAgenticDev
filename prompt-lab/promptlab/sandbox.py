"""Run model-written code in a throwaway directory and a separate process.

This is containment for honest mistakes (infinite loops, writes to the working
directory, crashes), not a security boundary: the subprocess runs as the same
user. It gets a scrubbed environment (no credentials or proxy settings), a temp
directory, and a timeout. Run the lab where model output may safely execute.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

TESTRUN = Path(__file__).with_name("testrun.py")
SAFE_ENV_KEYS = ("PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT")


def _env() -> dict:
    env = {k: os.environ[k] for k in SAFE_ENV_KEYS if k in os.environ}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONHASHSEED"] = "0"
    return env


def run_tests(files: dict[str, str], test_source: str, timeout: float = 30.0) -> dict:
    """Write `files` (name -> source) and the test file into a temp dir and run the tests.

    Returns the runner's JSON, plus "timeout": True or "crash": text when it did not finish.
    """
    with tempfile.TemporaryDirectory(prefix="promptlab-") as tmp:
        for name, source in files.items():
            Path(tmp, name).write_text(source, encoding="utf-8")
        test_path = Path(tmp, "test_model_written.py")
        test_path.write_text(test_source, encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "-I", str(TESTRUN), tmp, str(test_path)],
                                  cwd=tmp, env=_env(), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"passed": 0, "failed": 0, "errors": 0, "tests": [], "timeout": True}
        lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
        if not lines:
            return {"passed": 0, "failed": 0, "errors": 0, "tests": [], "crash": proc.stderr[-800:]}
        return json.loads(lines[-1])
