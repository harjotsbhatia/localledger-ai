"""Normalize, deduplicate and persist statement rows."""

from __future__ import annotations

import hashlib
import logging
from collections import Counter
from typing import Any

from pydantic import BaseModel

from localledger.ingestion.categorize import categorize
from localledger.ingestion.csv_parser import ColumnMapping, read_rows
from localledger.ingestion.normalize import (
    NormalizationError,
    clean_text,
    extract_merchant,
    fingerprint_text,
    parse_amount_minor,
    parse_date,
)

log = logging.getLogger(__name__)


class ImportResult(BaseModel):
    import_id: int
    rows_total: int
    rows_inserted: int
    rows_duplicate: int
    rows_invalid: int
    pending_settled: int
    invalid_row_numbers: list[int]


class NormalizedRow(BaseModel):
    posted_date: str
    amount_minor: int
    description_raw: str
    merchant: str
    category: str
    is_pending: bool
    is_transfer: bool
    fingerprint: str


def _row_amount(row: dict[str, str], mapping: ColumnMapping) -> int:
    if mapping.amount:
        amount = parse_amount_minor(row.get(mapping.amount, ""))
        return -amount if mapping.amount_convention == "positive_is_outflow" else amount
    debit = row.get(mapping.debit or "", "") if mapping.debit else ""
    credit = row.get(mapping.credit or "", "") if mapping.credit else ""
    if debit and credit:
        raise NormalizationError("both debit and credit present")
    if debit:
        return -abs(parse_amount_minor(debit))
    if credit:
        return abs(parse_amount_minor(credit))
    raise NormalizationError("empty amount")


def normalize_rows(
    records: list[dict[str, str]], mapping: ColumnMapping, account_id: int
) -> tuple[list[NormalizedRow], list[int]]:
    normalized: list[NormalizedRow] = []
    invalid: list[int] = []
    seen: Counter[tuple[str, int, str]] = Counter()
    for index, row in enumerate(records, start=2):  # 1-based, header is row 1
        try:
            posted = parse_date(row.get(mapping.date, ""), mapping.date_format).isoformat()
            amount = _row_amount(row, mapping)
            description = clean_text(row.get(mapping.description, ""))
            if not description:
                raise NormalizationError("empty description")
        except NormalizationError:
            invalid.append(index)
            continue
        status = row.get(mapping.status, "").strip().lower() if mapping.status else ""
        key = (posted, amount, fingerprint_text(description))
        occurrence = seen[key]
        seen[key] += 1
        # Occurrence index keeps genuine same-day repeats (two identical coffees) distinct
        # while re-imports of the same statement still collide. Pending status is excluded
        # so a pending row and its later posted version share a fingerprint.
        digest = hashlib.sha256(
            f"{account_id}|{posted}|{amount}|{key[2]}|{occurrence}".encode()
        ).hexdigest()
        category = categorize(description, amount)
        normalized.append(
            NormalizedRow(
                posted_date=posted,
                amount_minor=amount,
                description_raw=description,
                merchant=extract_merchant(description),
                category=category,
                is_pending=status in {"pending", "true", "yes", "p"},
                is_transfer=category == "Transfer",
                fingerprint=digest,
            )
        )
    return normalized, invalid


def import_csv(
    conn: Any, *, account_id: int, filename: str, content: str, mapping: ColumnMapping
) -> ImportResult:
    account = conn.execute(
        "SELECT id, currency FROM accounts WHERE id = ?", (account_id,)
    ).fetchone()
    if account is None:
        raise LookupError("Account not found.")
    headers, records = read_rows(content)
    for column in (mapping.date, mapping.description, mapping.amount, mapping.debit,
                   mapping.credit, mapping.status):
        if column and column not in headers:
            raise ValueError(f"Mapped column {column!r} is not in the file.")
    rows, invalid = normalize_rows(records, mapping, account_id)

    cursor = conn.execute(
        "INSERT INTO imports (account_id, filename, file_sha256, rows_total, rows_inserted,"
        " rows_duplicate, rows_invalid) VALUES (?, ?, ?, ?, 0, 0, ?)",
        (account_id, clean_text(filename, 120), hashlib.sha256(content.encode()).hexdigest(),
         len(records), len(invalid)),
    )
    import_id = cursor.lastrowid
    inserted = duplicate = settled = 0
    for row in rows:
        existing = conn.execute(
            "SELECT id, is_pending FROM transactions WHERE fingerprint = ?", (row.fingerprint,)
        ).fetchone()
        if existing is not None:
            duplicate += 1
            if existing["is_pending"] and not row.is_pending:
                conn.execute("UPDATE transactions SET is_pending = 0 WHERE id = ?",
                             (existing["id"],))
                settled += 1
            continue
        conn.execute(
            "INSERT INTO transactions (account_id, import_id, posted_date, amount_minor,"
            " currency, description_raw, merchant, category, is_pending, is_transfer,"
            " fingerprint) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (account_id, import_id, row.posted_date, row.amount_minor, account["currency"],
             row.description_raw, row.merchant, row.category, int(row.is_pending),
             int(row.is_transfer), row.fingerprint),
        )
        inserted += 1
    conn.execute(
        "UPDATE imports SET rows_inserted = ?, rows_duplicate = ? WHERE id = ?",
        (inserted, duplicate, import_id),
    )
    log.info("import id=%s total=%s inserted=%s duplicate=%s invalid=%s",
             import_id, len(records), inserted, duplicate, len(invalid))
    return ImportResult(
        import_id=import_id, rows_total=len(records), rows_inserted=inserted,
        rows_duplicate=duplicate, rows_invalid=len(invalid), pending_settled=settled,
        invalid_row_numbers=invalid[:50],
    )
