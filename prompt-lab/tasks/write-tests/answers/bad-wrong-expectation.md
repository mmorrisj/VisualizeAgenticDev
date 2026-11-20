```python
from datetime import date
from business_days import business_days_between


def test_week_excludes_end_date():
    # Wrong: the docstring says both ends count.
    assert business_days_between(date(2026, 1, 5), date(2026, 1, 9)) == 4
```
