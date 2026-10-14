#!/usr/bin/env python3
"""PreToolUse hook for Claude Code: block edits that weaken tests.

Same logic as mini-harness/hooks/no_test_weakening.py, adapted to Claude Code's
hook input: tool_name, and tool_input with file_path plus old_string/new_string
(Edit) or content (Write). Exit code 2 blocks the call; stderr goes to the model.
"""
import json
import re
import sys

event = json.load(sys.stdin)
inp = event.get("tool_input", {})
path = inp.get("file_path", "")
if not re.search(r"(^|/)(tests?/|test_[^/]*\.py$)", path):
    sys.exit(0)

old = inp.get("old_string", "")
new = inp.get("new_string", inp.get("content", ""))
real_asserts = re.compile(r"^\s*assert\s+(?!True\b)", re.MULTILINE)
weakening = re.compile(r"pytest\.(skip|xfail)|@pytest\.mark\.(skip|xfail)|^\s*assert\s+True\b",
                       re.MULTILINE)

if event.get("tool_name") == "Edit" and \
        len(real_asserts.findall(new)) < len(real_asserts.findall(old)):
    print(f"Blocked: this edit removes assertions from {path}. "
          "Fix the code under test instead.", file=sys.stderr)
    sys.exit(2)
if weakening.search(new) and not weakening.search(old):
    print(f"Blocked: this change adds a skip or an always-true assertion to {path}.",
          file=sys.stderr)
    sys.exit(2)
sys.exit(0)
