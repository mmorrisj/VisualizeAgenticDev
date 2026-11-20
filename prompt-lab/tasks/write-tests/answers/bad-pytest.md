```python
from datetime import date

import pytest

from business_days import business_days_between


@pytest.mark.parametrize("start,end,expected", [
    (date(2026, 1, 5), date(2026, 1, 9), 5),
    (date(2026, 1, 10), date(2026, 1, 11), 0),
])
def test_ranges(start, end, expected):
    assert business_days_between(start, end) == expected
```
