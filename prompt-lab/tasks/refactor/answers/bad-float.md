Simplified version using floats and Python's round():

```python
TAX = {"us-east": 0.0625, "us-west": 0.0725, "eu": 0.20, "uk": 0.20}


def line_total(item):
    total = item["unit_price"] * item["qty"]
    return total * 0.95 if item["qty"] >= 10 else total


def compute_invoice(customer, items, region, coupon=None):
    subtotal = sum(line_total(i) for i in items if i["qty"] > 0)
    if coupon == "WELCOME10" and customer.get("new"):
        subtotal *= 0.9
    elif coupon == "FLAT5" and subtotal > 50:
        subtotal -= 5
    subtotal = round(subtotal, 2)
    tax = round(subtotal * TAX.get(region, 0), 2)
    return {"customer": customer["id"], "subtotal": subtotal, "tax": tax, "total": subtotal + tax, "region": region}


def invoice_lines(items):
    return [(i["sku"], i["qty"], round(line_total(i), 2)) for i in items if i["qty"] > 0]


def tax_rate(region):
    return TAX.get(region, 0)


def format_invoice(invoice, currency="USD"):
    sym = {"USD": "$", "GBP": "£", "EUR": "€"}.get(currency, currency + " ")
    return (f"Invoice for {invoice['customer']}\nRegion: {invoice['region']}\n"
            f"Subtotal: {sym}{invoice['subtotal']:.2f}\nTax: {sym}{invoice['tax']:.2f}\nTotal: {sym}{invoice['total']:.2f}\n")
```
