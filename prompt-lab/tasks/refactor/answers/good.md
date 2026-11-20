Here is the refactored module. The line-total logic now lives in one helper, rounding is in one place, and every public function keeps its name and signature.

```python
"""Invoice calculations for the billing service."""
from decimal import ROUND_HALF_UP, Decimal

TAX = {"us-east": "0.0625", "us-west": "0.0725", "eu": "0.20", "uk": "0.20"}

BULK_QTY = 10
BULK_DISCOUNT = Decimal("0.05")
CENT = Decimal("0.01")
CURRENCY_SYMBOLS = {"USD": "$", "GBP": "£", "EUR": "€"}


def _money(amount):
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def _line_total(item):
    """Unrounded total for one line, with the bulk discount applied."""
    line = Decimal(str(item["unit_price"])) * item["qty"]
    if is_bulk(item["qty"]):
        line -= line * BULK_DISCOUNT
    return line


def _billable(items):
    return [item for item in items if item["qty"] > 0]


def _apply_coupon(subtotal, customer, coupon):
    if coupon == "WELCOME10" and customer.get("new") is True:
        return subtotal - subtotal * Decimal("0.10")
    if coupon == "FLAT5" and subtotal > Decimal("50"):
        return subtotal - Decimal("5")
    return subtotal


def compute_invoice(customer, items, *, region, coupon=None):
    subtotal = sum((_line_total(item) for item in _billable(items)), Decimal("0"))
    subtotal = _apply_coupon(subtotal, customer, coupon)
    tax = _money(subtotal * tax_rate(region))  # tax on the unrounded subtotal
    subtotal = _money(subtotal)
    return {"customer": customer["id"], "subtotal": subtotal, "tax": tax,
            "total": subtotal + tax, "region": region}


def invoice_lines(items):
    return [(item["sku"], item["qty"], _money(_line_total(item))) for item in _billable(items)]


def tax_rate(region):
    return Decimal(TAX.get(region, "0"))


def format_invoice(invoice, currency="USD"):
    sym = CURRENCY_SYMBOLS.get(currency, currency + " ")
    return (
        f"Invoice for {invoice['customer']}\n"
        f"Region: {invoice['region']}\n"
        f"Subtotal: {sym}{invoice['subtotal']}\n"
        f"Tax: {sym}{invoice['tax']}\n"
        f"Total: {sym}{invoice['total']}\n"
    )


def is_bulk(qty):
    return qty >= BULK_QTY
```
