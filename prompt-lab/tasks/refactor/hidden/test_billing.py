"""Hidden tests: the refactor must not change any behaviour."""
from decimal import Decimal

from billing import compute_invoice, format_invoice, invoice_lines, is_bulk, tax_rate

NEW = {"id": "c1", "new": True}
OLD = {"id": "c2"}


def items(*rows):
    return [{"sku": s, "qty": q, "unit_price": p} for s, q, p in rows]


def test_basic_total_with_tax():
    inv = compute_invoice(OLD, items(("A", 2, 10.00)), region="us-east")
    assert inv["subtotal"] == Decimal("20.00") and inv["tax"] == Decimal("1.25") and inv["total"] == Decimal("21.25")


def test_zero_and_negative_quantities_skipped():
    inv = compute_invoice(OLD, items(("A", 0, 5), ("B", -3, 5), ("C", 1, 5)), region="eu")
    assert inv["subtotal"] == Decimal("5.00")


def test_bulk_discount_at_ten():
    assert compute_invoice(OLD, items(("A", 10, 1.00)), region="none")["subtotal"] == Decimal("9.50")
    assert compute_invoice(OLD, items(("A", 9, 1.00)), region="none")["subtotal"] == Decimal("9.00")


def test_welcome_coupon_only_for_new_customers():
    assert compute_invoice(NEW, items(("A", 1, 100)), region="none", coupon="WELCOME10")["subtotal"] == Decimal("90.00")
    assert compute_invoice(OLD, items(("A", 1, 100)), region="none", coupon="WELCOME10")["subtotal"] == Decimal("100.00")


def test_flat5_needs_more_than_fifty():
    assert compute_invoice(OLD, items(("A", 1, 50)), region="none", coupon="FLAT5")["subtotal"] == Decimal("50.00")
    assert compute_invoice(OLD, items(("A", 1, 50.01)), region="none", coupon="FLAT5")["subtotal"] == Decimal("45.01")


def test_unknown_coupon_and_region_ignored():
    inv = compute_invoice(OLD, items(("A", 1, 10)), region="mars", coupon="BOGUS")
    assert inv["subtotal"] == Decimal("10.00") and inv["tax"] == Decimal("0.00")


def test_rounding_is_half_up_on_unrounded_subtotal():
    # Ties: subtotal 0.025 -> 0.03 and tax 0.005 -> 0.01 (half up; banker's rounding gives 0.02 and 0.00)
    inv = compute_invoice(OLD, items(("A", 1, "0.025")), region="eu")
    assert (inv["subtotal"], inv["tax"], inv["total"]) == (Decimal("0.03"), Decimal("0.01"), Decimal("0.04"))
    # 1.005 * 1 rounds half up to 1.01
    assert compute_invoice(OLD, items(("A", 1, "1.005")), region="none")["subtotal"] == Decimal("1.01")


def test_result_types_are_decimal_and_keys_unchanged():
    inv = compute_invoice(OLD, items(("A", 1, 3)), region="uk")
    assert set(inv) == {"customer", "subtotal", "tax", "total", "region"}
    assert all(isinstance(inv[k], Decimal) for k in ("subtotal", "tax", "total"))
    assert inv["customer"] == "c2" and inv["region"] == "uk"


def test_invoice_lines():
    assert invoice_lines(items(("A", 10, 1.00), ("B", 0, 4), ("C", 2, "0.125"))) == [
        ("A", 10, Decimal("9.50")), ("C", 2, Decimal("0.25"))]


def test_tax_rate_and_is_bulk():
    assert tax_rate("us-west") == Decimal("0.0725") and tax_rate("nowhere") == Decimal("0")
    assert is_bulk(10) is True and is_bulk(9) is False


def test_format_invoice_symbols():
    inv = compute_invoice(OLD, items(("A", 1, 10)), region="uk")
    text = format_invoice(inv, currency="GBP")
    assert text == "Invoice for c2\nRegion: uk\nSubtotal: £10.00\nTax: £2.00\nTotal: £12.00\n"
    assert "Total: CHF 12.00" in format_invoice(inv, currency="CHF")
    assert format_invoice(inv).startswith("Invoice for c2") and "$12.00" in format_invoice(inv)
