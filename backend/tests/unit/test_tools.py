import json

import pytest

from localledger.agent.tools import TOOLS, execute_tool, for_model, tool_specs
from tests.conftest import TODAY

EXPECTED_TOOLS = {
    "get_accounts", "search_transactions", "get_spending_by_category",
    "compare_spending_periods", "calculate_cash_flow", "identify_recurring_transactions",
    "get_monthly_summary",
}


def test_registry_exposes_exactly_the_documented_read_only_tools():
    assert set(TOOLS) == EXPECTED_TOOLS
    for spec in tool_specs():
        params = spec["function"]["parameters"]
        assert params["type"] == "object"
        assert all(p["type"] in {"string", "integer", "number"}
                   for p in params["properties"].values())
        json.dumps(spec)


def test_tools_do_not_write(conn):
    before = conn.total_changes
    for name in EXPECTED_TOOLS:
        args = {"period_a": "this_month", "period_b": "last_month"} if "compare" in name else (
            {"period": "last_month"} if name in {"get_spending_by_category",
                                                 "calculate_cash_flow"} else {})
        assert execute_tool(name, args, conn, TODAY).ok, name
    assert conn.total_changes == before


def test_restaurants_last_month(conn, dataset):
    out = execute_tool("get_spending_by_category",
                       {"period": "last_month", "category": "restaurants"}, conn, TODAY)
    assert out.ok
    assert out.result["total_spending_minor"] == dataset.golden["restaurants_last_month_minor"]
    assert out.result["period"] == {"label": "last month", "start_date": "2026-10-01",
                                    "end_date": "2026-10-31"}
    assert out.result["category"] == "Restaurants"


def test_category_with_no_data_returns_zero_not_error(conn):
    out = execute_tool("get_spending_by_category",
                       {"period": "2020-01", "category": "Travel"}, conn, TODAY)
    assert out.ok and out.result["total_spending_minor"] == 0


def test_compare_periods(conn, dataset):
    months = dataset.golden["months"]
    out = execute_tool("compare_spending_periods",
                       {"period_a": "2026-10", "period_b": "2026-09", "category": "Groceries"},
                       conn, TODAY)
    a = months["2026-10"]["by_category_minor"]["Groceries"]
    b = months["2026-09"]["by_category_minor"]["Groceries"]
    assert out.result["difference_a_minus_b_minor"] == a - b
    assert out.result["change_from_b_to_a_pct"] == round((a - b) * 100 / b, 1)


def test_cash_flow_and_monthly_summary(conn, dataset):
    october = dataset.golden["months"]["2026-10"]
    flow = execute_tool("calculate_cash_flow", {"period": "last_month"}, conn, TODAY).result
    assert flow["net_cash_flow_minor"] == october["net_minor"]
    summary = execute_tool("get_monthly_summary", {}, conn, TODAY).result
    assert summary["period"]["start_date"] == "2026-10-01"
    assert summary["spending_minor"] == october["spending_minor"]
    top = max(october["by_category_minor"].items(), key=lambda kv: kv[1])
    assert (summary["top_categories"][0]["category"], summary["top_categories"][0][
        "total_minor"]) == top


def test_search_tool_limits_rows_and_accepts_model_quirks(conn):
    out = execute_tool("search_transactions",
                       {"query": "starbucks", "limit": "3", "category": "", "min_amount": "5"},
                       conn, TODAY)
    assert out.ok and out.result["returned"] == 3 and out.result["total_matching"] > 3
    assert set(out.result["transactions"][0]) == {"date", "merchant", "amount_minor",
                                                  "category", "account", "pending"}


@pytest.mark.parametrize(("name", "args", "code"), [
    ("drop_tables", {}, "unknown_tool"),
    ("run_sql", {"query": "DELETE FROM transactions"}, "unknown_tool"),
    ("get_spending_by_category", "{not json", "malformed_arguments"),
    ("get_spending_by_category", [1, 2], "malformed_arguments"),
    ("get_spending_by_category", {}, "invalid_period"),
    ("get_spending_by_category", {"period": "last_month", "category": "crypto"},
     "unknown_category"),
    ("get_spending_by_category", {"period": "last_month", "sql": "1=1"}, "invalid_arguments"),
    ("get_spending_by_category", {"period": "sometime"}, "invalid_period"),
    ("search_transactions", {"limit": "many"}, "invalid_arguments"),
    ("search_transactions", {"start_date": "2026-01-01"}, "invalid_period"),
    ("calculate_cash_flow", {"start_date": "2026-02-01", "end_date": "2026-01-01"},
     "invalid_period"),
    ("compare_spending_periods", {"period_a": "last_month"}, "invalid_arguments"),
    ("get_monthly_summary", {"month": "this_year"}, "invalid_month"),
])
def test_invalid_calls_return_structured_errors(conn, name, args, code):
    out = execute_tool(name, args, conn, TODAY)
    assert not out.ok and out.result["error"]["code"] == code


def test_sql_injection_in_arguments_is_inert(conn):
    before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    out = execute_tool("search_transactions",
                       {"query": "'; DROP TABLE transactions; --"}, conn, TODAY)
    assert out.ok and out.result["total_matching"] == 0
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == before


def test_for_model_renders_exact_decimal_strings():
    assert for_model({"total_minor": 41237, "n": 3, "rows": [{"amount_minor": -5}]}) == {
        "total": "412.37", "n": 3, "rows": [{"amount": "-0.05"}]}


def test_model_quirks_seen_in_evaluation_are_tolerated(conn, dataset):
    # Junk dates next to a valid period, the string "null", and out-of-range integers.
    out = execute_tool("get_spending_by_category",
                       {"category": "null", "end_date": "last_month", "period": "last_month"},
                       conn, TODAY)
    assert out.ok
    assert out.result["total_spending_minor"] == dataset.golden["months"]["2026-10"][
        "spending_minor"]
    big = execute_tool("search_transactions", {"query": "netflix", "limit": "100"}, conn, TODAY)
    assert big.ok and big.result["returned"] == 13
    rec = execute_tool("identify_recurring_transactions", {"lookback_months": "0"}, conn, TODAY)
    assert rec.ok and rec.result["lookback_months"] == 3
    # Without a period, junk dates are still rejected.
    bad = execute_tool("calculate_cash_flow", {"end_date": "last_month"}, conn, TODAY)
    assert not bad.ok
