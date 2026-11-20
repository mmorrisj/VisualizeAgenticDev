"""Invoice calculations for the billing service."""
from decimal import Decimal, ROUND_HALF_UP

TAX = {"us-east": "0.0625", "us-west": "0.0725", "eu": "0.20", "uk": "0.20"}


def compute_invoice(customer, items, *, region, coupon=None):
    # items is a list of dicts with sku, qty, unit_price
    subtotal = Decimal("0")
    for i in range(len(items)):
        it = items[i]
        if it["qty"] <= 0:
            continue
        price = Decimal(str(it["unit_price"]))
        line = price * it["qty"]
        if it["qty"] >= 10:
            line = line - (line * Decimal("0.05"))
        subtotal = subtotal + line
    if coupon != None:
        if coupon == "WELCOME10":
            if customer.get("new") == True:
                subtotal = subtotal - subtotal * Decimal("0.10")
        elif coupon == "FLAT5":
            if subtotal > Decimal("50"):
                subtotal = subtotal - Decimal("5")
    if region in TAX:
        rate = Decimal(TAX[region])
    else:
        rate = Decimal("0")
    tax = subtotal * rate
    tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    subtotal = subtotal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    total = subtotal + tax
    return {"customer": customer["id"], "subtotal": subtotal, "tax": tax,
            "total": total, "region": region}


def invoice_lines(items):
    out = []
    for i in range(len(items)):
        it = items[i]
        if it["qty"] <= 0:
            continue
        price = Decimal(str(it["unit_price"]))
        line = price * it["qty"]
        if it["qty"] >= 10:
            line = line - (line * Decimal("0.05"))
        line = line.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        out.append((it["sku"], it["qty"], line))
    return out


def tax_rate(region):
    if region in TAX:
        r = Decimal(TAX[region])
    else:
        r = Decimal("0")
    return r


def format_invoice(invoice, currency="USD"):
    s = ""
    s = s + "Invoice for " + str(invoice["customer"]) + "\n"
    s = s + "Region: " + invoice["region"] + "\n"
    if currency == "USD":
        sym = "$"
    elif currency == "GBP":
        sym = "£"
    elif currency == "EUR":
        sym = "€"
    else:
        sym = currency + " "
    s = s + "Subtotal: " + sym + str(invoice["subtotal"]) + "\n"
    s = s + "Tax: " + sym + str(invoice["tax"]) + "\n"
    s = s + "Total: " + sym + str(invoice["total"]) + "\n"
    return s


def is_bulk(qty):
    if qty >= 10:
        return True
    else:
        return False
