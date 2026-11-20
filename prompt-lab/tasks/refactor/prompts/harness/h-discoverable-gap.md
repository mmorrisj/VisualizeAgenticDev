Refactor billing.py to remove the duplicated logic and make it easier to maintain.

- Keep is_bulk: other services outside this repository call it, even though nothing here does.
- Standard library only, and the code must run on Python 3.10.
