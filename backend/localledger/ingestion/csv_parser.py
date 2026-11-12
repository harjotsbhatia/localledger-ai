"""CSV statement parsing with explicit, user-correctable column mapping."""

from __future__ import annotations

import csv
import io
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from localledger.ingestion.normalize import DATE_FORMATS, detect_date_format

MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_ROWS = 100_000


class CsvError(ValueError):
    pass


class ColumnMapping(BaseModel):
    date: str
    description: str
    amount: str | None = None
    debit: str | None = None
    credit: str | None = None
    status: str | None = None
    date_format: str = "YYYY-MM-DD"
    amount_convention: Literal["negative_is_outflow", "positive_is_outflow"] = (
        "negative_is_outflow"
    )

    @model_validator(mode="after")
    def _check(self) -> ColumnMapping:
        if not self.amount and not (self.debit or self.credit):
            raise ValueError("Map either an amount column or debit/credit columns.")
        if self.date_format not in DATE_FORMATS:
            raise ValueError(f"Unsupported date format: {self.date_format}")
        return self


class CsvPreview(BaseModel):
    headers: list[str]
    sample_rows: list[dict[str, str]]
    row_count: int
    suggested_mapping: ColumnMapping | None
    date_formats: list[str] = Field(default_factory=lambda: list(DATE_FORMATS))


_SYNONYMS: dict[str, tuple[str, ...]] = {
    "date": ("date", "posted date", "posting date", "transaction date", "trans date"),
    "description": ("description", "memo", "details", "payee", "name", "merchant", "narrative"),
    "amount": ("amount", "amount (usd)", "transaction amount"),
    "debit": ("debit", "withdrawal", "withdrawals", "money out", "debit amount"),
    "credit": ("credit", "deposit", "deposits", "money in", "credit amount"),
    "status": ("status", "state", "pending"),
}


def read_rows(content: str) -> tuple[list[str], list[dict[str, str]]]:
    if len(content.encode("utf-8", errors="ignore")) > MAX_CSV_BYTES:
        raise CsvError("File is larger than the 10 MB import limit.")
    text = content.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if len(rows) < 2:
        raise CsvError("The file needs a header row and at least one transaction.")
    if len(rows) - 1 > MAX_ROWS:
        raise CsvError(f"The file has more than {MAX_ROWS} rows.")
    headers = [h.strip() for h in rows[0]]
    if len(set(headers)) != len(headers) or not all(headers):
        raise CsvError("Header names must be unique and non-empty.")
    records = [
        {h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(headers)}
        for row in rows[1:]
    ]
    return headers, records


def suggest_mapping(headers: list[str], records: list[dict[str, str]]) -> ColumnMapping | None:
    found: dict[str, str] = {}
    lowered = {h.lower(): h for h in headers}
    for field, names in _SYNONYMS.items():
        for name in names:
            if name in lowered:
                found[field] = lowered[name]
                break
    if "date" not in found or "description" not in found:
        return None
    if "amount" not in found and not ("debit" in found or "credit" in found):
        return None
    date_format = detect_date_format([r[found["date"]] for r in records[:200]]) or "YYYY-MM-DD"
    if "amount" in found:
        found.pop("debit", None)
        found.pop("credit", None)
    return ColumnMapping(date_format=date_format, **found)


def preview(content: str) -> CsvPreview:
    headers, records = read_rows(content)
    return CsvPreview(
        headers=headers,
        sample_rows=records[:8],
        row_count=len(records),
        suggested_mapping=suggest_mapping(headers, records),
    )
