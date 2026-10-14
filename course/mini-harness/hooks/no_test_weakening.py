#!/usr/bin/env python3
"""pre_tool hook: block edits that weaken tests.

A path rule can forbid editing tests/ entirely. Sometimes you DO want the agent
to add tests, so this hook inspects the content of the edit instead: it blocks
edits to test files that remove assertions or add skips.

Protocol: JSON on stdin; exit 0 to continue; exit 2 to block (stderr = reason).
"""
import json
import re
import sys

event = json.load(sys.stdin)
if event.get("tool") != "edit_file":
    sys.exit(0)

inp = event.get("input", {})
path = inp.get("path", "")
if not re.search(r"(^|/)(tests?/|test_[^/]*\.py$)", path):
    sys.exit(0)

old, new = inp.get("old_text", ""), inp.get("new_text", "")
real_asserts = re.compile(r"^\s*assert\s+(?!True\b)", re.MULTILINE)
weakening = re.compile(r"pytest\.(skip|xfail)|@pytest\.mark\.(skip|xfail)|^\s*assert\s+True\b",
                       re.MULTILINE)

if len(real_asserts.findall(new)) < len(real_asserts.findall(old)):
    print(f"Blocked: this edit removes assertions from {path}. "
          "Fix the code under test instead of the test.", file=sys.stderr)
    sys.exit(2)
if weakening.search(new) and not weakening.search(old):
    print(f"Blocked: this edit adds a skip or an always-true assertion to {path}.",
          file=sys.stderr)
    sys.exit(2)
sys.exit(0)
