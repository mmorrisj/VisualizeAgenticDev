#!/usr/bin/env python3
"""Print only failing tests and their assertion lines, to keep tool output small.

Runs practice-app's run_tests.py in the current directory and condenses the
output. A full verbose test log can be thousands of tokens; this is usually
a few dozen.
"""
import subprocess
import sys

proc = subprocess.run([sys.executable, "run_tests.py"], capture_output=True, text=True)
lines = proc.stdout.splitlines()
summary = lines[-1] if lines else "no output"
failures, current = [], None
for line in lines:
    if line.startswith("--- ") and line.endswith(" ---"):
        current = line.strip("- ")
    elif current and line.strip().startswith("assert "):
        failures.append(f"{current}: {line.strip()}")
        current = None
print(summary)
for f in failures:
    print("  " + f)
sys.exit(proc.returncode)
