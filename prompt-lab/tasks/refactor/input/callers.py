"""How other services call the billing module (excerpts)."""
from billing import compute_invoice, format_invoice, invoice_lines, tax_rate

def checkout(customer, cart, region, coupon=None):
    invoice = compute_invoice(customer, cart, region=region, coupon=coupon)
    return format_invoice(invoice, currency="GBP" if region == "uk" else "USD")

def receipt_lines(cart):
    return [f"{sku} x{qty}: {amount}" for sku, qty, amount in invoice_lines(cart)]

def quote_tax(region, amount):
    return amount * tax_rate(region)
