```python
from datetime import date

from business_days import business_days_between

MON = date(2026, 1, 5)
TUE = date(2026, 1, 6)
FRI = date(2026, 1, 9)
SAT = date(2026, 1, 10)
SUN = date(2026, 1, 11)
NEXT_MON = date(2026, 1, 12)


def test_full_week_counts_both_ends():
    assert business_days_between(MON, FRI) == 5


def test_weekend_days_do_not_count():
    assert business_days_between(FRI, NEXT_MON) == 2
    assert business_days_between(SAT, SUN) == 0


def test_single_weekday_is_one():
    assert business_days_between(TUE, TUE) == 1


def test_single_weekend_day_is_zero():
    assert business_days_between(SAT, SAT) == 0


def test_friday_counts():
    assert business_days_between(FRI, FRI) == 1


def test_weekday_holiday_is_excluded():
    assert business_days_between(MON, FRI, holidays={TUE}) == 4


def test_weekend_holiday_changes_nothing():
    assert business_days_between(MON, NEXT_MON, holidays={SAT}) == 6


def test_start_after_end_is_zero():
    assert business_days_between(NEXT_MON, MON) == 0
```
