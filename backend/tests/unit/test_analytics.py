from datetime import date

import pytest

from localledger.analytics import core
from localledger.analytics.periods import PeriodError, resolve_period, resolve_range
from tests.conftest import TODAY


@pytest.mark.parametrize(("period", "start", "end"), [
    ("this_month", date(2026, 11, 1), date(2026, 11, 10)),
    ("last_month", date(2026, 10, 1), date(2026, 10, 31)),
    ("last_30_days", date(2026, 10, 12), date(2026, 11, 10)),
    ("last_6_months", date(2026, 5, 1), date(2026, 10, 31)),
    ("this_year", date(2026, 1, 1), date(2026, 11, 10)),
    ("last_year", date(2025, 1, 1), date(2025, 12, 31)),
    ("2026-02", date(2026, 2, 1), date(2026, 2, 28)),
    ("2024-02", date(2024, 2, 1), date(2024, 2, 29)),
    ("2025", date(2025, 1, 1), date(2025, 12, 31)),
    ("Last Month", date(2026, 10, 1), date(2026, 10, 31)),
])
def test_resolve_period(period, start, end):
    rng = resolve_period(period, TODAY)
    assert (rng.start, rng.end) == (start, end)


def test_last_month_across_year_boundary():
    rng = resolve_period("last_month", date(2027, 1, 3))
    assert (rng.start, rng.end) == (date(2026, 12, 1), date(2026, 12, 31))


@pytest.mark.parametrize("bad", ["yesterdayish", "2026-13", "last_0_days", ""])
def test_bad_periods(bad):
    with pytest.raises(PeriodError):
        resolve_range(bad or None, None, None, TODAY)


def test_range_requires_both_dates():
    with pytest.raises(PeriodError):
        resolve_range(None, date(2026, 1, 1), None, TODAY)
    with pytest.raises(PeriodError):
        resolve_range(None, date(2026, 2, 1), date(2026, 1, 1), TODAY)


def test_spending_by_category_matches_golden_for_every_month(conn, dataset):
    for month, expected in dataset.golden["months"].items():
        result = core.spending_by_category(conn, resolve_period(month, TODAY))
        actual = {c["category"]: c["total_minor"] for c in result["categories"]}
        assert actual == expected["by_category_minor"], month
        assert result["total_spending_minor"] == expected["spending_minor"], month


def test_cash_flow_matches_golden_for_every_month(conn, dataset):
    for month, expected in dataset.golden["months"].items():
        flow = core.cash_flow(conn, resolve_period(month, TODAY))
        assert flow["income_minor"] == expected["income_minor"], month
        assert flow["spending_minor"] == expected["spending_minor"], month
        assert flow["net_cash_flow_minor"] == expected["net_minor"], month


def test_restaurants_last_month_is_the_golden_figure(conn, dataset):
    result = core.spending_by_category(conn, resolve_period("last_month", TODAY), "Restaurants")
    assert result["total_spending_minor"] == dataset.golden["restaurants_last_month_minor"] > 0


def test_transfers_are_excluded_from_income_and_spending(conn):
    flow = core.cash_flow(conn, resolve_period("all_time", TODAY))
    with_transfers = conn.execute(
        "SELECT SUM(amount_minor) FROM transactions WHERE category != 'Transfer'").fetchone()[0]
    assert flow["net_cash_flow_minor"] == with_transfers
    cats = core.spending_by_category(conn, resolve_period("all_time", TODAY))["categories"]
    assert not {"Transfer", "Income"} & {c["category"] for c in cats}


def test_monthly_trend_matches_golden(conn, dataset):
    trend = core.monthly_trend(conn, resolve_period("all_time", TODAY))
    assert [p["month"] for p in trend] == sorted(dataset.golden["months"])
    for point in trend:
        assert point["net_cash_flow_minor"] == dataset.golden["months"][point["month"]]["net_minor"]


def test_recurring_detection_finds_fixed_subscriptions(conn):
    found = {r["merchant"]: r for r in core.recurring_transactions(conn, TODAY, 6)}
    assert found["Netflix.Com"]["cadence"] == "monthly"
    assert found["Netflix.Com"]["typical_amount_minor"] == 1549
    assert found["Netflix.Com"]["estimated_annual_cost_minor"] == 1549 * 12
    assert found["Spotify Usa"]["typical_amount_minor"] == 1199
    assert found["Rent Payment Oakwood Property Mgmt"]["typical_amount_minor"] == 185000
    assert found["City Electric Utility"]["amount_varies"] is True
    assert "Starbucks Coffee" not in found  # frequent but irregular


def test_search_filters_and_like_escaping(conn):
    hits = core.search_transactions(conn, query="netflix")
    assert hits["total_count"] == 13 and len(hits["transactions"]) == 13
    assert core.search_transactions(conn, query="%")["total_count"] == 0
    assert core.search_transactions(conn, query="_")["total_count"] == 0
    big = core.search_transactions(conn, min_amount_minor=180000, category="Housing")
    assert big["total_count"] == 13
    page = core.search_transactions(conn, limit=5, offset=5)
    assert len(page["transactions"]) == 5


def test_named_period_wins_over_model_computed_dates():
    # Observed with llama3.2:3b: period=last_month plus a wrong start_date.
    rng = resolve_range("last_month", date(2026, 9, 1), date(2026, 10, 31), TODAY)
    assert (rng.start, rng.end) == (date(2026, 10, 1), date(2026, 10, 31))
