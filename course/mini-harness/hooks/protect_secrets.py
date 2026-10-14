#!/usr/bin/env python3
"""pre_tool hook: block any tool call whose input mentions a .env file.

Deny rules match one field (a path, or a command prefix). This hook looks at
the WHOLE input, so it also catches `cat .env`, `-d @.env`, `source .env`, and
`grep TOKEN .env`, which a rule like run_command(curl *) would not.

Protocol: JSON on stdin; exit 0 to continue; exit 2 to block (stderr = reason).
"""
import json
import re
import sys

event = json.load(sys.stdin)
text = json.dumps(event.get("input", {}))

if re.search(r"(^|[\s/@\"'=])\.env(\.[\w-]+)?\b", text):
    print("Blocked: this action references a .env secrets file. "
          "Ask the user for any configuration values you need.", file=sys.stderr)
    sys.exit(2)
sys.exit(0)
