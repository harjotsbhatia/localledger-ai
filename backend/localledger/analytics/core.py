"""Deterministic financial calculations over the local database.

Conventions (see ARCHITECTURE.md):
- Amounts are integer minor units; negative = money out.
- Transfers between own accounts (incl. credit-card payments) are excluded everywhere.
- Spending in a category is net of refunds: -(sum of amounts in that category).
- Income is the sum of the Income category. Net cash flow = income - spending.
- Pending transactions are included and counted separately.
All SQL is static and parameterized. Nothing here writes.
"""

from __future__ import annotations

from datetime import date, timedelta
from statistics import median
from typing import Any

from localledger.analytics.periods import DateRange

_SPEND_FILTER = "is_transfer = 0 AND category NOT IN ('Income', 'Transfer')"


def _pct(part: int, whole: int) -> float:
    return round(part * 100 / whole, 1) if whole else 0.0


def primary_currency(conn: Any) -> str:
    row = conn.execute(
        "SELECT currency FROM accounts GROUP BY currency ORDER BY COUNT(*) DESC LIMIT 1"
    ).fetchone()
    return row["currency"] if row else "USD"


def accounts_summary(conn: Any) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT a.id, a.name, a.institution, a.type, a.currency, a.connector,"
        " COUNT(t.id) AS transaction_count, MIN(t.posted_date) AS first_date,"
        " MAX(t.posted_date) AS last_date, COALESCE(SUM(t.amount_minor), 0) AS net_flow_minor"
        " FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id"
        " GROUP BY a.id ORDER BY a.name"
    ).fetchall()
    return [dict(row) for row in rows]


def spending_by_category(
    conn: Any, rng: DateRange, category: str | None = None
) -> dict[str, Any]:
    sql = (
        "SELECT category, -SUM(amount_minor) AS total_minor, COUNT(*) AS transaction_count"
        f" FROM transactions WHERE posted_date BETWEEN ? AND ? AND {_SPEND_FILTER}"
    )
    params: list[Any] = [rng.start.isoformat(), rng.end.isoformat()]
    if category:
        sql += " AND category = ?"
        params.append(category)
    sql += " GROUP BY category ORDER BY total_minor DESC, category"
    rows = [dict(row) for row in conn.execute(sql, params).fetchall()]
    total = sum(row["total_minor"] for row in rows)
    for row in rows:
        row["share_pct"] = _pct(row["total_minor"], total)
    return {"total_spending_minor": total, "categories": rows}


def cash_flow(conn: Any, rng: DateRange) -> dict[str, Any]:
    row = conn.execute(
        "SELECT"
        " COALESCE(SUM(CASE WHEN category = 'Income' THEN amount_minor END), 0) AS income,"
        " COALESCE(-SUM(CASE WHEN category != 'Income' THEN amount_minor END), 0) AS spending,"
        " COUNT(*) AS n, COALESCE(SUM(is_pending), 0) AS pending"
        " FROM transactions WHERE posted_date BETWEEN ? AND ?"
        " AND is_transfer = 0 AND category != 'Transfer'",
        (rng.start.isoformat(), rng.end.isoformat()),
    ).fetchone()
    net = row["income"] - row["spending"]
    return {
        "income_minor": row["income"],
        "spending_minor": row["spending"],
        "net_cash_flow_minor": net,
        "savings_rate_pct": _pct(net, row["income"]) if row["income"] > 0 else None,
        "transaction_count": row["n"],
        "pending_count": row["pending"],
    }


def monthly_trend(conn: Any, rng: DateRange) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT substr(posted_date, 1, 7) AS month,"
        " COALESCE(SUM(CASE WHEN category = 'Income' THEN amount_minor END), 0) AS income_minor,"
        " COALESCE(-SUM(CASE WHEN category != 'Income' THEN amount_minor END), 0)"
        "   AS spending_minor"
        " FROM transactions WHERE posted_date BETWEEN ? AND ?"
        " AND is_transfer = 0 AND category != 'Transfer' GROUP BY month ORDER BY month",
        (rng.start.isoformat(), rng.end.isoformat()),
    ).fetchall()
    return [
        {**dict(row), "net_cash_flow_minor": row["income_minor"] - row["spending_minor"]}
        for row in rows
    ]


def top_merchants(conn: Any, rng: DateRange, limit: int = 5) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT merchant, category, -SUM(amount_minor) AS total_minor,"
        " COUNT(*) AS transaction_count"
        f" FROM transactions WHERE posted_date BETWEEN ? AND ? AND {_SPEND_FILTER}"
        " GROUP BY merchant HAVING total_minor > 0 ORDER BY total_minor DESC, merchant LIMIT ?",
        (rng.start.isoformat(), rng.end.isoformat(), limit),
    ).fetchall()
    return [dict(row) for row in rows]


def search_transactions(
    conn: Any,
    *,
    rng: DateRange | None = None,
    query: str | None = None,
    category: str | None = None,
    account_id: int | None = None,
    min_amount_minor: int | None = None,
    max_amount_minor: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    where = ["1 = 1"]
    params: list[Any] = []
    if rng:
        where.append("t.posted_date BETWEEN ? AND ?")
        params += [rng.start.isoformat(), rng.end.isoformat()]
    if query:
        escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        where.append("(t.description_raw LIKE ? ESCAPE '\\' OR t.merchant LIKE ? ESCAPE '\\')")
        params += [f"%{escaped}%", f"%{escaped}%"]
    if category:
        where.append("t.category = ?")
        params.append(category)
    if account_id is not None:
        where.append("t.account_id = ?")
        params.append(account_id)
    if min_amount_minor is not None:
        where.append("ABS(t.amount_minor) >= ?")
        params.append(min_amount_minor)
    if max_amount_minor is not None:
        where.append("ABS(t.amount_minor) <= ?")
        params.append(max_amount_minor)
    clause = " AND ".join(where)  # built only from the fixed fragments above
    totals = conn.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(t.amount_minor), 0) AS total"
        f" FROM transactions t WHERE {clause}",
        params,
    ).fetchone()
    rows = conn.execute(
        "SELECT t.id, t.posted_date, t.amount_minor, t.currency, t.description_raw,"
        " t.merchant, t.category, t.is_pending, t.is_transfer, t.account_id,"
        " a.name AS account_name"
        f" FROM transactions t JOIN accounts a ON a.id = t.account_id WHERE {clause}"
        " ORDER BY t.posted_date DESC, t.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
    return {
        "total_count": totals["n"],
        "net_amount_minor": totals["total"],
        "transactions": [
            {**dict(r), "is_pending": bool(r["is_pending"]), "is_transfer": bool(r["is_transfer"])}
            for r in rows
        ],
    }


_CADENCES = (("weekly", 6, 8, 52), ("biweekly", 13, 16, 26), ("monthly", 27, 33, 12),
             ("quarterly", 85, 95, 4), ("yearly", 350, 380, 1))


def recurring_transactions(conn: Any, as_of: date, lookback_months: int = 6) -> list[dict]:
    start = as_of - timedelta(days=31 * lookback_months)
    rows = conn.execute(
        "SELECT merchant, category, posted_date, amount_minor FROM transactions"
        " WHERE posted_date BETWEEN ? AND ? AND amount_minor < 0 AND is_transfer = 0"
        " AND category != 'Transfer' ORDER BY merchant, posted_date",
        (start.isoformat(), as_of.isoformat()),
    ).fetchall()
    groups: dict[str, list[Any]] = {}
    for row in rows:
        groups.setdefault(row["merchant"], []).append(row)
    found: list[dict[str, Any]] = []
    for merchant, items in groups.items():
        if len(items) < 3:
            continue
        dates = [date.fromisoformat(i["posted_date"]) for i in items]
        gaps = [(b - a).days for a, b in zip(dates, dates[1:], strict=False)]
        mid = median(gaps)
        cadence = next((c for c in _CADENCES if c[1] <= mid <= c[2]), None)
        if cadence is None:
            continue
        regular = sum(cadence[1] - 2 <= g <= cadence[2] + 2 for g in gaps)
        if regular / len(gaps) < 0.8:
            continue
        amounts = [-i["amount_minor"] for i in items]
        typical = int(median(amounts))
        found.append({
            "merchant": merchant,
            "category": items[-1]["category"],
            "cadence": cadence[0],
            "typical_amount_minor": typical,
            "amount_varies": (max(amounts) - min(amounts)) > typical * 0.1,
            "occurrences": len(items),
            "last_date": dates[-1].isoformat(),
            "next_expected_date": (dates[-1] + timedelta(days=round(mid))).isoformat(),
            "estimated_annual_cost_minor": typical * cadence[3],
        })
    found.sort(key=lambda r: (-r["estimated_annual_cost_minor"], r["merchant"]))
    return found
