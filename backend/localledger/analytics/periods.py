"""Deterministic date-range resolution. The language model never computes dates."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

NAMED_PERIODS = (
    "this_month", "last_month", "last_30_days", "last_90_days", "last_6_months",
    "last_12_months", "this_year", "last_year", "all_time",
)


class PeriodError(ValueError):
    pass


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date
    label: str


def _month_range(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _shift_month(day: date, months: int) -> date:
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


def resolve_period(period: str, today: date) -> DateRange:
    key = period.strip().lower().replace(" ", "_").replace("-", "_")
    if key == "this_month":
        return DateRange(today.replace(day=1), today, "this month")
    if key in {"last_month", "previous_month"}:
        first = _shift_month(today, -1)
        return DateRange(*_month_range(first.year, first.month), "last month")
    if match := re.fullmatch(r"last_(\d{1,3})_days", key):
        days = int(match.group(1))
        if days < 1:
            raise PeriodError("Number of days must be positive.")
        return DateRange(today - timedelta(days=days - 1), today, f"last {days} days")
    if match := re.fullmatch(r"last_(\d{1,2})_months", key):
        months = int(match.group(1))
        if months < 1:
            raise PeriodError("Number of months must be positive.")
        start = _shift_month(today, -months)
        end = today.replace(day=1) - timedelta(days=1)
        return DateRange(start, end, f"last {months} full months")
    if key == "this_year":
        return DateRange(date(today.year, 1, 1), today, "this year")
    if key == "last_year":
        return DateRange(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), "last year")
    if key == "all_time":
        return DateRange(date(1970, 1, 1), today, "all time")
    raw = period.strip()
    if match := re.fullmatch(r"(\d{4})-(\d{1,2})", raw):
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            raise PeriodError("Month must be between 01 and 12.")
        return DateRange(*_month_range(year, month), f"{year:04d}-{month:02d}")
    if match := re.fullmatch(r"(\d{4})", raw):
        year = int(match.group(1))
        return DateRange(date(year, 1, 1), date(year, 12, 31), str(year))
    raise PeriodError(
        f"Unknown period {period!r}. Use one of {', '.join(NAMED_PERIODS)}, "
        "a month like 2026-03, or a year like 2026."
    )


def resolve_range(
    period: str | None, start_date: date | None, end_date: date | None, today: date
) -> DateRange:
    # A named period always wins. Small models often send a correct period name together
    # with dates they computed themselves (and got wrong); dates are only trusted alone.
    if period:
        return resolve_period(period, today)
    if start_date and end_date:
        if start_date > end_date:
            raise PeriodError("start_date must not be after end_date.")
        return DateRange(start_date, end_date, f"{start_date} to {end_date}")
    if start_date or end_date:
        raise PeriodError("Provide both start_date and end_date, or use period instead.")
    raise PeriodError("Provide a period (e.g. last_month) or start_date and end_date.")
