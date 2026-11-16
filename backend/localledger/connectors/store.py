"""Applies a provider-neutral SyncBatch to the local database, idempotently."""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from pydantic import BaseModel

from localledger.connectors.base import RemoteAccount, SyncBatch
from localledger.ingestion.categorize import categorize
from localledger.ingestion.normalize import clean_text, extract_merchant

log = logging.getLogger(__name__)

_ACCOUNT_TYPES = {"checking", "savings", "credit_card", "other"}


class SyncResult(BaseModel):
    connection_id: int
    accounts: int
    added: int
    updated: int
    removed: int
    messages: list[str]


def _fingerprint(connection_id: int, external_id: str) -> str:
    return hashlib.sha256(f"connection:{connection_id}|{external_id}".encode()).hexdigest()


def _unique_name(conn: Any, account: RemoteAccount, provider: str) -> str:
    base = clean_text(account.name, 60) or "Account"
    candidates = [base]
    if account.mask:
        candidates.append(f"{base} ••{clean_text(account.mask, 6)}")
    candidates += [f"{base} ({provider} {n})" for n in range(1, 50)]
    for name in candidates:
        if not conn.execute("SELECT 1 FROM accounts WHERE name = ?", (name,)).fetchone():
            return name
    raise RuntimeError("could not find a free account name")


def _upsert_account(conn: Any, connection_id: int, provider: str,
                    account: RemoteAccount) -> int:
    row = conn.execute(
        "SELECT id FROM accounts WHERE connection_id = ? AND external_id = ?",
        (connection_id, account.external_id),
    ).fetchone()
    if row:
        return row["id"]
    currency = account.currency if len(account.currency) == 3 and account.currency.isalpha() \
        else "USD"
    cursor = conn.execute(
        "INSERT INTO accounts (name, institution, type, currency, connector, connection_id,"
        " external_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (_unique_name(conn, account, provider), clean_text(account.institution, 80),
         account.type if account.type in _ACCOUNT_TYPES else "other", currency.upper(),
         provider, connection_id, account.external_id),
    )
    return cursor.lastrowid


def apply_batch(conn: Any, connection_id: int, provider: str, batch: SyncBatch) -> SyncResult:
    account_ids = {a.external_id: _upsert_account(conn, connection_id, provider, a)
                   for a in batch.accounts}
    currencies = {row["id"]: row["currency"] for row in conn.execute(
        "SELECT id, currency FROM accounts WHERE connection_id = ?", (connection_id,))}
    added = updated = removed = 0

    def delete(external_id: str) -> int:
        return conn.execute(
            "DELETE FROM transactions WHERE fingerprint = ?",
            (_fingerprint(connection_id, external_id),),
        ).rowcount

    for tx in batch.upserts:
        account_id = account_ids.get(tx.account_external_id)
        if account_id is None:
            continue  # transaction for an account the provider did not describe
        if tx.replaces_external_id and tx.replaces_external_id != tx.external_id:
            removed += delete(tx.replaces_external_id)
        description = clean_text(tx.description) or "Unknown"
        category = categorize(description, tx.amount_minor)
        values = (tx.posted_date.isoformat(), tx.amount_minor, description,
                  extract_merchant(description), category, int(tx.pending),
                  int(category == "Transfer"))
        fingerprint = _fingerprint(connection_id, tx.external_id)
        existing = conn.execute(
            "SELECT id FROM transactions WHERE fingerprint = ?", (fingerprint,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE transactions SET posted_date = ?, amount_minor = ?,"
                " description_raw = ?, merchant = ?, category = ?, is_pending = ?,"
                " is_transfer = ? WHERE id = ?", (*values, existing["id"]))
            updated += 1
        else:
            conn.execute(
                "INSERT INTO transactions (posted_date, amount_minor, description_raw,"
                " merchant, category, is_pending, is_transfer, account_id, currency,"
                " fingerprint, external_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (*values, account_id, currencies[account_id], fingerprint, tx.external_id))
            added += 1
    for external_id in batch.removed_external_ids:
        removed += delete(external_id)
    log.info("sync connection=%s accounts=%s added=%s updated=%s removed=%s",
             connection_id, len(account_ids), added, updated, removed)
    return SyncResult(connection_id=connection_id, accounts=len(account_ids), added=added,
                      updated=updated, removed=removed,
                      messages=[clean_text(m, 300) for m in batch.messages][:10])
