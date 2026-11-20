Refactor billing.py to remove the duplicated logic and make it easier to maintain. Behaviour must not change.

- callers.py imports compute_invoice, format_invoice, invoice_lines and tax_rate, and passes region by keyword. It must keep working unchanged.
- Money is Decimal with ROUND_HALF_UP. Tax is computed on the unrounded subtotal, then both are rounded.
- compute_invoice must keep returning a dict with the keys customer, subtotal, tax, total, region.
- Keep every public function with its exact name and signature, including is_bulk: other services outside this repository call it, even though nothing here does.
- Standard library only, and the code must run on Python 3.10.
