"""Token accounting (spec section 8).

Only provider-reported counts are recorded as counts. A value the provider did
not report is stored as NOT_REPORTED, never filled with an estimate; the course
estimator may be shown alongside, labelled as an estimate.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

NOT_REPORTED = "not reported"
INCLUDED_IN_OUTPUT = "included in output"

# A reported count, or one of the two labels above.
Count = int | str


@dataclass
class Usage:
    """One request's token usage, normalized across providers.

    `input` is uncached input only; cached input is in `cache_read` and
    `cache_write`, so `total_input()` adds the three back together.
    """

    input: Count = NOT_REPORTED
    output: Count = NOT_REPORTED
    reasoning: Count = NOT_REPORTED
    cache_read: Count = NOT_REPORTED
    cache_write: Count = NOT_REPORTED
    synthetic: bool = False  # True for the mock backend: numbers are made up

    def total_input(self) -> int | None:
        """All input tokens, cached or not; None if input was not reported."""
        if not isinstance(self.input, int):
            return None
        return self.input + sum(v for v in (self.cache_read, self.cache_write) if isinstance(v, int))

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_tokens(obj) -> int:
    """The course harness's estimator (mini-harness/backends.py): about 4 characters per token.

    Never stored as a reported count; used only for labelled estimates and the mock backend.
    """
    text = obj if isinstance(obj, str) else json.dumps(obj)
    return max(1, len(text) // 4)


def int_or_none(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
