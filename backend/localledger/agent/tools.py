"""Read-only, schema-validated tools the language model may call.

The model chooses a tool and arguments; every number comes from analytics.core.
There is deliberately no SQL, shell, file or network tool.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from localledger.analytics import core
from localledger.analytics.periods import DateRange, PeriodError, resolve_period, resolve_range
from localledger.ingestion.categorize import CATEGORIES, resolve_category

_PERIOD_HELP = (
    "Named period: this_month, last_month, last_30_days, last_90_days, last_6_months, "
    "last_12_months, this_year, last_year, all_time; or a month like 2026-03; or a year "
    "like 2026. The server resolves it to exact dates."
)
_CATEGORY_HELP = "One of: " + ", ".join(CATEGORIES) + "."


class ToolError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        # Small local models often send "" or "null" for optional arguments.
        if isinstance(data, dict):
            return {
                k: (None if isinstance(v, str) and v.strip().lower() in {"", "null", "none"}
                    else v)
                for k, v in data.items()
            }
        return data


def _clamped(lo: int, hi: int, default: int) -> Any:
    """Out-of-range or unparsable integers are clamped rather than rejected: the intent is
    clear and a rejection costs a small model a round it often does not recover from."""

    def clamp(value: Any) -> Any:
        if value is None:
            return default
        try:
            return max(lo, min(hi, int(value)))
        except (TypeError, ValueError):
            return value  # let normal validation report it

    return BeforeValidator(clamp)


class _RangeArgs(_Args):
    @model_validator(mode="before")
    @classmethod
    def _period_wins(cls, data: Any) -> Any:
        # Observed with llama3.2:3b: period="last_month" plus end_date="last_month" or dates
        # it computed itself. A named period is authoritative, so the dates are dropped.
        if isinstance(data, dict) and isinstance(data.get("period"), str) and data[
                "period"].strip().lower() not in {"", "null", "none"}:
            return {k: v for k, v in data.items() if k not in {"start_date", "end_date"}}
        return data

    period: str | None = Field(None, description=_PERIOD_HELP)
    start_date: date | None = Field(None, description=(
        "Only when the user states exact calendar dates (YYYY-MM-DD). Omit if period is "
        "set; period takes precedence."))
    end_date: date | None = Field(None, description="Only together with start_date.")


class NoArgs(_Args):
    pass


class SearchArgs(_RangeArgs):
    query: str | None = Field(None, max_length=80, description="Text in merchant/description.")
    category: str | None = Field(None, description=_CATEGORY_HELP)
    min_amount: Decimal | None = Field(None, ge=0, description="Minimum absolute amount.")
    max_amount: Decimal | None = Field(None, ge=0, description="Maximum absolute amount.")
    limit: Annotated[int, _clamped(1, 25, 10)] = Field(10, ge=1, le=25)


class SpendingArgs(_RangeArgs):
    category: str | None = Field(None, description="Optional single category. " + _CATEGORY_HELP)


class CompareArgs(_Args):
    period_a: str = Field(description="First period. " + _PERIOD_HELP)
    period_b: str = Field(description="Second period, same format as period_a.")
    category: str | None = Field(None, description="Optional single category. " + _CATEGORY_HELP)


class CashFlowArgs(_RangeArgs):
    pass


class RecurringArgs(_Args):
    lookback_months: Annotated[int, _clamped(3, 24, 6)] = Field(6, ge=3, le=24)


class MonthlySummaryArgs(_Args):
    month: str = Field("last_month", description="this_month, last_month, or YYYY-MM.")


def _category(name: str | None) -> str | None:
    if name is None:
        return None
    resolved = resolve_category(name)
    if resolved is None:
        raise ToolError("unknown_category", f"Unknown category {name!r}. {_CATEGORY_HELP}")
    return resolved


def _range_dict(rng: DateRange) -> dict[str, str]:
    return {"label": rng.label, "start_date": rng.start.isoformat(),
            "end_date": rng.end.isoformat()}


def _to_minor(value: Decimal | None) -> int | None:
    return None if value is None else int((value * 100).to_integral_value())


def _get_accounts(conn: Any, args: NoArgs, today: date) -> dict[str, Any]:
    return {"accounts": core.accounts_summary(conn)}


def _search(conn: Any, args: SearchArgs, today: date) -> dict[str, Any]:
    rng = None
    if args.period or args.start_date or args.end_date:
        rng = resolve_range(args.period, args.start_date, args.end_date, today)
    found = core.search_transactions(
        conn, rng=rng, query=args.query, category=_category(args.category),
        min_amount_minor=_to_minor(args.min_amount), max_amount_minor=_to_minor(args.max_amount),
        limit=args.limit,
    )
    rows = [
        {"date": t["posted_date"], "merchant": t["merchant"], "amount_minor": t["amount_minor"],
         "category": t["category"], "account": t["account_name"], "pending": t["is_pending"]}
        for t in found["transactions"]
    ]
    return {
        "period": _range_dict(rng) if rng else {"label": "all time"},
        "total_matching": found["total_count"],
        "net_amount_of_all_matching_minor": found["net_amount_minor"],
        "returned": len(rows),
        "transactions": rows,
    }


def _spending(conn: Any, args: SpendingArgs, today: date) -> dict[str, Any]:
    rng = resolve_range(args.period, args.start_date, args.end_date, today)
    category = _category(args.category)
    result = core.spending_by_category(conn, rng, category)
    out: dict[str, Any] = {"period": _range_dict(rng)}
    if category:
        row = next(iter(result["categories"]), None)
        out.update(category=category,
                   total_spending_minor=row["total_minor"] if row else 0,
                   transaction_count=row["transaction_count"] if row else 0)
    else:
        out.update(result)
    return out


def _compare(conn: Any, args: CompareArgs, today: date) -> dict[str, Any]:
    category = _category(args.category)
    a, b = resolve_period(args.period_a, today), resolve_period(args.period_b, today)
    total_a = core.spending_by_category(conn, a, category)["total_spending_minor"]
    total_b = core.spending_by_category(conn, b, category)["total_spending_minor"]
    diff = total_a - total_b
    return {
        "category": category or "all spending",
        "period_a": {**_range_dict(a), "total_spending_minor": total_a},
        "period_b": {**_range_dict(b), "total_spending_minor": total_b},
        "difference_a_minus_b_minor": diff,
        "change_from_b_to_a_pct": round(diff * 100 / total_b, 1) if total_b else None,
    }


def _cash_flow(conn: Any, args: CashFlowArgs, today: date) -> dict[str, Any]:
    rng = resolve_range(args.period, args.start_date, args.end_date, today)
    return {"period": _range_dict(rng), **core.cash_flow(conn, rng)}


def _recurring(conn: Any, args: RecurringArgs, today: date) -> dict[str, Any]:
    items = core.recurring_transactions(conn, today, args.lookback_months)
    return {
        "lookback_months": args.lookback_months,
        "recurring": items,
        "estimated_total_annual_cost_minor": sum(i["estimated_annual_cost_minor"] for i in items),
    }


def _monthly_summary(conn: Any, args: MonthlySummaryArgs, today: date) -> dict[str, Any]:
    rng = resolve_period(args.month, today)
    if (rng.start.year, rng.start.month) != (rng.end.year, rng.end.month):
        raise ToolError("invalid_month", "month must be this_month, last_month, or YYYY-MM.")
    spending = core.spending_by_category(conn, rng)
    return {
        "period": _range_dict(rng),
        **core.cash_flow(conn, rng),
        "top_categories": spending["categories"][:5],
        "top_merchants": core.top_merchants(conn, rng, 5),
    }


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    args_model: type[_Args]
    handler: Callable[[Any, Any, date], dict[str, Any]]


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool("get_accounts", "List the user's accounts with transaction counts and date "
             "coverage.", NoArgs, _get_accounts),
        Tool("search_transactions", "Find individual transactions by text, category, date "
             "range or amount. Returns at most `limit` rows plus the count and net total of "
             "all matches. Not for income or spending totals: use calculate_cash_flow or "
             "get_spending_by_category for those.", SearchArgs, _search),
        Tool("get_spending_by_category", "Total spending for a period, broken down by "
             "category, or for one category if `category` is given. Use this for questions "
             "like 'how much did I spend on restaurants last month'.", SpendingArgs, _spending),
        Tool("compare_spending_periods", "Compare spending between two periods, optionally "
             "for one category.", CompareArgs, _compare),
        Tool("calculate_cash_flow", "Income, spending, net cash flow and savings rate for a "
             "period.", CashFlowArgs, _cash_flow),
        Tool("identify_recurring_transactions", "Detect subscriptions and other recurring "
             "charges with cadence and estimated annual cost.", RecurringArgs, _recurring),
        Tool("get_monthly_summary", "Overview of one calendar month: income, spending, net, "
             "top categories and top merchants.", MonthlySummaryArgs, _monthly_summary),
    )
}


def _simplify(schema: dict[str, Any]) -> dict[str, Any]:
    """Flatten pydantic's JSON schema into the plain shape local models handle best."""
    props = {}
    for name, spec in schema.get("properties", {}).items():
        options = [o for o in spec.get("anyOf", [spec]) if o.get("type") != "null"]
        chosen = options[0] if options else {"type": "string"}
        if len(options) > 1:  # e.g. Decimal -> number|string
            chosen = next((o for o in options if o.get("type") == "number"), options[0])
        prop = {"type": chosen.get("type", "string")}
        if "description" in spec:
            prop["description"] = spec["description"]
        props[name] = prop
    return {"type": "object", "properties": props, "required": schema.get("required", [])}


def tool_specs() -> list[dict[str, Any]]:
    return [
        {"type": "function",
         "function": {"name": t.name, "description": t.description,
                      "parameters": _simplify(t.args_model.model_json_schema())}}
        for t in TOOLS.values()
    ]


@dataclass
class ToolOutcome:
    ok: bool
    result: dict[str, Any]


def execute_tool(name: str, raw_args: Any, conn: Any, today: date) -> ToolOutcome:
    tool = TOOLS.get(name)
    if tool is None:
        return ToolOutcome(False, {"error": {
            "code": "unknown_tool",
            "message": f"No tool named {name!r}. Available: {', '.join(TOOLS)}."}})
    if isinstance(raw_args, str):
        try:
            raw_args = json.loads(raw_args) if raw_args.strip() else {}
        except json.JSONDecodeError:
            return ToolOutcome(False, {"error": {
                "code": "malformed_arguments", "message": "Arguments were not valid JSON."}})
    if raw_args is None:
        raw_args = {}
    if not isinstance(raw_args, dict):
        return ToolOutcome(False, {"error": {
            "code": "malformed_arguments", "message": "Arguments must be a JSON object."}})
    try:
        args = tool.args_model.model_validate(raw_args)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}"
            for e in exc.errors()[:5]
        )
        allowed = ", ".join(tool.args_model.model_fields) or "(none)"
        return ToolOutcome(False, {"error": {
            "code": "invalid_arguments",
            "message": f"{problems}. Allowed arguments: {allowed}."}})
    try:
        return ToolOutcome(True, tool.handler(conn, args, today))
    except ToolError as exc:
        return ToolOutcome(False, {"error": {"code": exc.code, "message": exc.message}})
    except PeriodError as exc:
        return ToolOutcome(False, {"error": {"code": "invalid_period", "message": str(exc)}})


def for_model(value: Any) -> Any:
    """Render a tool result for the model: `*_minor` integers become decimal strings."""
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if key.endswith("_minor") and isinstance(item, int):
                sign = "-" if item < 0 else ""
                out[key[:-6]] = f"{sign}{abs(item) // 100}.{abs(item) % 100:02d}"
            else:
                out[key] = for_model(item)
        return out
    if isinstance(value, list):
        return [for_model(v) for v in value]
    return value
