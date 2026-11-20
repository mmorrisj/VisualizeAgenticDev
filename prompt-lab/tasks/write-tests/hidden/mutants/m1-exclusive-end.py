"""Business-day arithmetic for SLA timers."""
from datetime import date, timedelta


def business_days_between(start: date, end: date, holidays=frozenset()) -> int:
    """Count business days from start to end, counting both ends.

    A business day is Monday to Friday and not in `holidays`.
    Holidays that fall on a weekend are ignored (they are not business days anyway).
    If start is after end, the result is 0.
    """
    if start > end:
        return 0
    count = 0
    day = start
    while day < end:
        if day.weekday() < 5 and day not in holidays:
            count += 1
        day += timedelta(days=1)
    return count
