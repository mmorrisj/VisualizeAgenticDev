Write tests for business_days_between in business_days.py that would catch bugs in it.

- Cover every rule in the docstring: both ends count; Saturdays and Sundays never count; a holiday on a weekend changes nothing; start after end gives 0; a single day gives 1 or 0 depending on the day.
- Pin exact expected numbers using real 2026 dates.
- The CI runner has no pytest: use the standard library only, either plain functions with assert or unittest.
- Write each case as its own test_ function, so a failure points at one behaviour.
