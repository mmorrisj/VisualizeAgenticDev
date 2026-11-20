```python
from datetime import date
from business_days import business_days_between


def test_counts_something():
    assert business_days_between(date(2026, 1, 5), date(2026, 1, 16)) > 0
```
