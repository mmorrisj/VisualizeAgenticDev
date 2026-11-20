Refactor billing.py to remove the duplicated logic and make it easier to maintain.

- callers.py imports compute_invoice, format_invoice, invoice_lines and tax_rate, and passes region by keyword. It must keep working unchanged.
- Money is Decimal with ROUND_HALF_UP. Tax is computed on the unrounded subtotal, then both are rounded.
- compute_invoice must keep returning a dict with the keys customer, subtotal, tax, total, region.
