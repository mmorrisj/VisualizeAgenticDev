Refactor billing.py to remove the duplicated line-total logic and make it easier to maintain.

Constraints:
- Behaviour must not change at all. Keep Decimal arithmetic and ROUND_HALF_UP rounding, and keep the order of rounding: tax is computed on the unrounded subtotal, then both are rounded.
- compute_invoice must keep returning a dict with the keys customer, subtotal, tax, total, region.
- Keep every public function with its exact name and signature. That includes is_bulk: other services outside this repository call it, even though nothing here does.
- callers.py shows how this module is used; it must keep working unchanged.
- Standard library only, and the code must run on Python 3.10.

Return the complete module in a single ```python code block.
