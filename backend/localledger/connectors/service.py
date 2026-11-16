"""Connection lifecycle: connect, sync, disconnect.

Network calls happen outside any database transaction, and credentials move only between
the connector and the keychain.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from localledger.connectors.base import BankConnector, ConnectorError
from localledger.connectors.store import SyncResult, apply_batch
from localledger.ingestion.normalize import clean_text
from localledger.security.secrets import SecretStore, connection_secret_name
from localledger.storage.db import Database

INITIAL_HISTORY_DAYS = 90
OVERLAP_DAYS = 5


class Connection(BaseModel):
    id: int
    provider: str
    label: str
    status: str
    last_synced_at: str | None
    last_error: str | None
    account_count: int
    transaction_count: int


def list_connections(conn: Any) -> list[Connection]:
    rows = conn.execute(
        "SELECT c.id, c.provider, c.label, c.status, c.last_synced_at, c.last_error,"
        " COUNT(DISTINCT a.id) AS account_count, COUNT(t.id) AS transaction_count"
        " FROM connections c LEFT JOIN accounts a ON a.connection_id = c.id"
        " LEFT JOIN transactions t ON t.account_id = a.id GROUP BY c.id ORDER BY c.id"
    ).fetchall()
    return [Connection(**dict(row)) for row in rows]


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class ConnectionService:
    def __init__(self, db: Database, secrets: SecretStore,
                 connectors: dict[str, BankConnector]) -> None:
        self.db = db
        self.secrets = secrets
        self.connectors = connectors

    def _connector(self, provider: str) -> BankConnector:
        connector = self.connectors.get(provider)
        if connector is None:
            raise ConnectorError("unknown_provider", "That provider is not available.")
        return connector

    def connect(self, provider: str, params: dict[str, str]) -> int:
        new = self._connector(provider).connect(params)
        with self.db.connect() as conn:
            connection_id = conn.execute(
                "INSERT INTO connections (provider, label) VALUES (?, ?)",
                (provider, clean_text(new.label, 80) or provider),
            ).lastrowid
        try:
            self.secrets.set(connection_secret_name(connection_id), new.secret)
        except Exception:
            with self.db.connect() as conn:
                conn.execute("DELETE FROM connections WHERE id = ?", (connection_id,))
            raise
        return connection_id

    def sync(self, connection_id: int, today: date, *, force: bool = False) -> SyncResult:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM connections WHERE id = ?",
                               (connection_id,)).fetchone()
        if row is None:
            raise LookupError("Connection not found.")
        connector = self._connector(row["provider"])
        interval = connector.info.min_sync_interval_seconds
        if row["last_attempt_at"] and interval and not force:
            elapsed = datetime.now(UTC) - datetime.fromisoformat(row["last_attempt_at"])
            if elapsed < timedelta(seconds=interval):
                wait = int((timedelta(seconds=interval) - elapsed).total_seconds() // 60) + 1
                raise ConnectorError(
                    "rate_limited",
                    f"{connector.info.display_name} limits how often data can be fetched. "
                    f"Try again in about {wait} minutes.")
        secret = self.secrets.get(connection_secret_name(connection_id))
        if secret is None:
            self._record(connection_id, "needs_attention",
                         "Credentials are missing from the keychain. Reconnect this bank.")
            raise ConnectorError("missing_credentials",
                                 "Credentials are missing from the keychain. Reconnect this "
                                 "bank.", needs_attention=True)
        since = today - timedelta(days=INITIAL_HISTORY_DAYS)
        if row["last_synced_at"]:
            last = datetime.fromisoformat(row["last_synced_at"]).date()
            since = max(since, last - timedelta(days=OVERLAP_DAYS))
        with self.db.connect() as conn:
            conn.execute("UPDATE connections SET last_attempt_at = ? WHERE id = ?",
                         (_now(), connection_id))
        try:
            batch = connector.sync(secret, row["sync_cursor"], since, today)
        except ConnectorError as exc:
            self._record(connection_id,
                         "needs_attention" if exc.needs_attention else "error", exc.message)
            raise
        with self.db.connect() as conn:
            result = apply_batch(conn, connection_id, row["provider"], batch)
            conn.execute(
                "UPDATE connections SET status = 'active', last_error = NULL,"
                " last_synced_at = ?, sync_cursor = ? WHERE id = ?",
                (_now(), batch.cursor, connection_id))
        return result

    def disconnect(self, connection_id: int, *, delete_data: bool,
                   offline: bool = False) -> list[str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT provider FROM connections WHERE id = ?",
                               (connection_id,)).fetchone()
        if row is None:
            raise LookupError("Connection not found.")
        notes: list[str] = []
        name = connection_secret_name(connection_id)
        secret = self.secrets.get(name)
        connector = self.connectors.get(row["provider"])
        if secret and connector and not offline:
            try:
                note = connector.disconnect(secret)
                if note:
                    notes.append(note)
            except ConnectorError as exc:
                notes.append("Local credentials were removed, but the provider could not be "
                             f"told to revoke access: {exc.message}")
        elif secret and offline:
            notes.append("Offline mode is on, so access was not revoked at the provider. "
                         "Local credentials were removed.")
        # Local credentials are always destroyed, whatever the provider said.
        self.secrets.delete(name)
        with self.db.connect() as conn:
            if delete_data:
                conn.execute("DELETE FROM accounts WHERE connection_id = ?", (connection_id,))
            conn.execute("DELETE FROM connections WHERE id = ?", (connection_id,))
        return notes

    def forget_all_credentials(self) -> None:
        """Used by delete-all-data: remove every connection's keychain item."""
        with self.db.connect() as conn:
            ids = [r["id"] for r in conn.execute("SELECT id FROM connections")]
        for connection_id in ids:
            self.secrets.delete(connection_secret_name(connection_id))

    def _record(self, connection_id: int, status: str, error: str) -> None:
        with self.db.connect() as conn:
            conn.execute("UPDATE connections SET status = ?, last_error = ? WHERE id = ?",
                         (status, clean_text(error, 300), connection_id))
