from datetime import date

import pytest

from localledger.ingestion.categorize import categorize, resolve_category
from localledger.ingestion.normalize import (
    NormalizationError,
    clean_text,
    detect_date_format,
    extract_merchant,
    parse_amount_minor,
    parse_date,
)


@pytest.mark.parametrize(("raw", "expected"), [
    ("12.34", 1234), ("-12.34", -1234), ("$1,234.56", 123456), ("(45.00)", -4500),
    ("45.00-", -4500), ("12.3", 1230), ("7", 700), ("+3.50", 350), ("19.99 DR", -1999),
    ("19.99 CR", 1999), ("-$0.05", -5), (".99", 99), ("0.10", 10), ("1,000,000.01", 100000001),
])
def test_parse_amount(raw, expected):
    assert parse_amount_minor(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12.345", "1.2.3", "=SUM(A1)", "12,34", "4,12",
                                 "1,23,456.00", "1.234,56"])
def test_parse_amount_rejects(raw):
    with pytest.raises(NormalizationError):
        parse_amount_minor(raw)


def test_amounts_never_use_float_rounding():
    # 0.1 + 0.2 style drift cannot happen: values are exact integers.
    assert parse_amount_minor("0.10") + parse_amount_minor("0.20") == 30
    assert parse_amount_minor("1.15") == 115  # float(1.15)*100 == 114.99999999999999


def test_parse_date_formats():
    assert parse_date("2026-03-09", "YYYY-MM-DD") == date(2026, 3, 9)
    assert parse_date("03/09/2026", "MM/DD/YYYY") == date(2026, 3, 9)
    assert parse_date("09/03/2026", "DD/MM/YYYY") == date(2026, 3, 9)
    with pytest.raises(NormalizationError):
        parse_date("2026-13-40", "YYYY-MM-DD")


def test_detect_date_format():
    assert detect_date_format(["2026-01-31", "2026-02-01"]) == "YYYY-MM-DD"
    assert detect_date_format(["01/31/2026", "02/01/2026"]) == "MM/DD/YYYY"
    assert detect_date_format(["31/01/2026", "01/02/2026"]) == "DD/MM/YYYY"
    assert detect_date_format(["nope"]) is None


def test_clean_text_strips_control_characters():
    assert clean_text("  A\x00B\tC\n‮D  ") == "A B C D"
    assert len(clean_text("x" * 500)) == 200


def test_extract_merchant():
    assert extract_merchant("STARBUCKS COFFEE #1234 SEATTLE WA") == "Starbucks Coffee"
    assert extract_merchant("POS DEBIT CHIPOTLE 0456 AUSTIN TX") == "Chipotle"
    assert extract_merchant("") == "Unknown"


@pytest.mark.parametrize(("description", "amount", "category"), [
    ("STARBUCKS COFFEE #1234", -500, "Restaurants"),
    ("ACME CORP PAYROLL DIRECT DEP", 325000, "Income"),
    ("RENT PAYMENT OAKWOOD PROPERTY MGMT", -185000, "Housing"),
    ("CURRENT ACCOUNT ADJUSTMENT", -100, "Other"),
    ("CREDIT CARD PAYMENT THANK YOU", -50000, "Transfer"),
    ("UBER EATS ORDER", -2300, "Restaurants"),
    ("UBER TRIP", -1500, "Transport"),
    ("MYSTERY DEPOSIT", 5000, "Income"),
    ("MONTHLY MAINTENANCE FEE", -1200, "Fees"),
])
def test_categorize(description, amount, category):
    assert categorize(description, amount) == category


def test_resolve_category_aliases():
    assert resolve_category("restaurants") == "Restaurants"
    assert resolve_category("Dining") == "Restaurants"
    assert resolve_category("crypto") is None
