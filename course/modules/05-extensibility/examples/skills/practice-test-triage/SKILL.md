---
name: practice-test-triage
description: Diagnose failing tests in practice-app. Use when tests fail or the user asks why a test is failing. Summarizes failures compactly and finds the root cause without modifying tests.
---

# Test triage for practice-app

1. Get a compact failure summary instead of the full test output:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/failures.py
   ```

2. For each failing test, read the test function and the code it calls. Read only those functions, not whole directories.

3. Report, for each failure:
   - the test name and the assertion that failed,
   - the file and line of the code responsible,
   - a one-sentence root cause.

4. Do not modify any file under `tests/`. If a test itself looks wrong, say so and explain why, and let the user decide.
