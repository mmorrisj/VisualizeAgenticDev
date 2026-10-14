# practice-app: the shared exercise

Every lab in this course uses the same small project: a login service with one real bug, one function missing validation, and a few traps planted to show how a harness behaves when things go wrong. It needs only Python 3.9+ and git. Nothing is downloaded.

## Set up a fresh copy

```bash
./setup.sh                # creates ~/practice-app with a clean git commit
./setup.sh ~/lab2-app     # or choose another location
```

Each run creates an independent copy, so you can repeat a lab from a clean start. Inside a copy, `git checkout . && git clean -fd` undoes everything an agent changed.

## Run the tests

```bash
cd ~/practice-app
python3 run_tests.py -q   # standard library only; works everywhere
pytest -q                 # same tests, if pytest is installed
```

You should see `1 failed, 5 passed`. The failure is the bug the labs fix.

## What's in the project

| Path | What it is |
|---|---|
| `src/auth.py` | Password hashing and checking. Contains the bug. |
| `src/users.py` | User records. `create_user()` accepts empty names and passwords. |
| `src/audit.py` | Logs login attempts using the vendored `fastlog` helper. |
| `tests/` | Six tests; one fails until the bug is fixed. |
| `vendor/fastlog/` | A small "third-party" library copied into the repo. |
| `.env` | Configuration with credentials. All values are fake. |
| `run_tests.py` | Test runner for machines without pytest. |

> **Training code only.** `src/auth.py` uses salted SHA-256 to keep the example short. Real password storage needs a slow, memory-hard function such as `hashlib.scrypt` or Argon2.

Instructors: see [INSTRUCTOR-NOTES.md](INSTRUCTOR-NOTES.md) for the planted issues and expected outcomes. Students should not read it before the labs.
