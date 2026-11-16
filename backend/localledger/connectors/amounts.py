"""Exact conversion of provider amounts to integer minor units."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Any

from localledger.connectors.base import ConnectorError


def to_minor(value: Any) -> int:
    """Accepts a Decimal, int or numeric string. Floats are rejected by design: callers
    must parse JSON with ``parse_float=Decimal`` so no binary rounding ever occurs."""
    if isinstance(value, float):
        raise TypeError("amounts must not be parsed as float")
    try:
        number = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ConnectorError("bad_amount", "The provider sent an unreadable amount.") from exc
    if not number.is_finite() or abs(number) > Decimal(10) ** 11:
        raise ConnectorError("bad_amount", "The provider sent an unreadable amount.")
    return int((number * 100).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
