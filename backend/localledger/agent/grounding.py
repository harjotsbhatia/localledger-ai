"""Checks that monetary figures in the model's reply were actually produced by a tool."""

from __future__ import annotations

import re
from typing import Any

_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)"
_MONEY = re.compile(
    rf"(?<![\w.,])(\$\s?{_NUM}(?:\.\d{{1,2}})?(?!\d)|{_NUM}\.\d{{2}}(?![\d%]))"
)


def figures_in_text(text: str) -> list[tuple[str, int, bool]]:
    """Return (as written, value in minor units, has_cents) for each monetary figure."""
    out = []
    for match in _MONEY.finditer(text):
        raw = match.group(1)
        digits = raw.replace("$", "").replace(",", "").strip()
        whole, _, frac = digits.partition(".")
        out.append((raw, int(whole) * 100 + int(frac.ljust(2, "0") or 0), bool(frac)))
    return out


def verified_amounts(value: Any) -> set[int]:
    found: set[int] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_minor") and isinstance(item, int):
                found.add(abs(item))
            else:
                found |= verified_amounts(item)
    elif isinstance(value, list):
        for item in value:
            found |= verified_amounts(item)
    return found


def check_grounding(reply: str, tool_results: list[dict[str, Any]]) -> list[str]:
    """Return the figures in `reply` that no tool result supports (empty = grounded).

    Exact matches pass. Whole-dollar figures pass if they equal a tool amount rounded
    or truncated to dollars. Anything else (including sums the model did itself) is flagged.
    """
    allowed = verified_amounts(tool_results)
    rounded = {round(a / 100) * 100 for a in allowed} | {a // 100 * 100 for a in allowed}
    unverified = []
    for raw, minor, has_cents in figures_in_text(reply):
        if minor in allowed or (not has_cents and minor in rounded):
            continue
        unverified.append(raw)
    return unverified
