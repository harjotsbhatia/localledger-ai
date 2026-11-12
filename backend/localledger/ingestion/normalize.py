"""Pure normalization helpers for untrusted statement text."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS: dict[str, str] = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "MM/DD/YYYY": "%m/%d/%Y",
    "DD/MM/YYYY": "%d/%m/%Y",
    "MM/DD/YY": "%m/%d/%y",
    "YYYY/MM/DD": "%Y/%m/%d",
    "DD-MM-YYYY": "%d-%m-%Y",
    "MMM DD, YYYY": "%b %d, %Y",
}

_CURRENCY_CHARS = re.compile(r"[$€£¥\s]|USD|EUR|GBP|CAD", re.IGNORECASE)
_MAX_MINOR = 10**13  # sanity bound: 100 billion major units


class NormalizationError(ValueError):
    pass


def parse_amount_minor(raw: str) -> int:
    """Parse a statement amount into integer minor units (cents) without floats.

    Accepts "$1,234.56", "-12.34", "(12.34)", "12.34-", "12.34 CR", "12.34 DR".
    """
    text = (raw or "").strip()
    if not text:
        raise NormalizationError("empty amount")
    negative = False
    upper = text.upper()
    if upper.endswith("DR"):
        negative, text = True, text[:-2]
    elif upper.endswith("CR"):
        text = text[:-2]
    text = _CURRENCY_CHARS.sub("", text)
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1]
    if text.endswith("-"):
        negative, text = not negative, text[:-1]
    if text.startswith("-"):
        negative, text = not negative, text[1:]
    elif text.startswith("+"):
        text = text[1:]
    # Commas are accepted only as well-formed thousands separators. "4,12" (a European
    # decimal comma) is rejected rather than silently read as 412.00.
    if "," in text:
        if not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d{1,2})?", text):
            raise NormalizationError("ambiguous comma in amount")
        text = text.replace(",", "")
    if not re.fullmatch(r"\d+(\.\d{1,2})?|\.\d{1,2}", text):
        raise NormalizationError("unrecognized amount")
    try:
        minor = int((Decimal(text) * 100).to_integral_exact())
    except InvalidOperation as exc:  # pragma: no cover - regex guards this
        raise NormalizationError("unrecognized amount") from exc
    if minor > _MAX_MINOR:
        raise NormalizationError("amount out of range")
    return -minor if negative else minor


def parse_date(raw: str, date_format: str) -> date:
    fmt = DATE_FORMATS.get(date_format)
    if fmt is None:
        raise NormalizationError(f"unsupported date format {date_format!r}")
    try:
        return datetime.strptime((raw or "").strip(), fmt).date()  # noqa: DTZ007 - date only
    except ValueError as exc:
        raise NormalizationError("unrecognized date") from exc


def detect_date_format(samples: list[str]) -> str | None:
    """Return the first known format that parses every non-empty sample."""
    values = [s.strip() for s in samples if s and s.strip()]
    if not values:
        return None
    for name in DATE_FORMATS:
        try:
            for value in values:
                parse_date(value, name)
        except NormalizationError:
            continue
        return name
    return None


def clean_text(raw: str, max_len: int = 200) -> str:
    """Strip control characters and collapse whitespace. Content stays untrusted data."""
    text = unicodedata.normalize("NFKC", raw or "")
    text = "".join(ch if unicodedata.category(ch)[0] != "C" else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()[:max_len]


_PREFIXES = re.compile(
    r"^(POS (DEBIT|PURCHASE)|DEBIT CARD PURCHASE|CHECKCARD|PURCHASE AUTHORIZED ON \d{2}/\d{2}"
    r"|RECURRING PAYMENT|ACH (DEBIT|CREDIT)|SQ \*|TST\* ?|PAYPAL \*)\s*[-:]?\s*",
    re.IGNORECASE,
)
_SUFFIXES = re.compile(r"(\s+#?\d{3,}.*$)|(\s+[A-Z]{2}\s*$)|(\s+\d{2}/\d{2}\s*$)")


def extract_merchant(description: str) -> str:
    text = clean_text(description)
    text = _PREFIXES.sub("", text)
    text = _SUFFIXES.sub("", text.upper())
    text = re.sub(r"[*]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -")
    return text.title()[:80] if text else "Unknown"


def fingerprint_text(description: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", clean_text(description).upper()).strip()
