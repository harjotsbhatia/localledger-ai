"""Common connector contract.

Analytics and the AI layer only ever see normalized rows in the database, so adding
Plaid or SimpleFIN (Phase 2) means implementing this protocol and nothing else.
Only the CSV connector exists today; no bank network connector is implemented.
"""

from __future__ import annotations

from typing import Any, Protocol

from localledger.ingestion.importer import ImportResult


class Connector(Protocol):
    id: str
    display_name: str
    uses_network: bool
    """True when data transits a third party (bank aggregator). Shown to the user."""

    def sync(self, conn: Any, *, account_id: int, **kwargs: Any) -> ImportResult: ...


class CsvConnector:
    id = "csv"
    display_name = "CSV file import"
    uses_network = False

    def sync(self, conn: Any, *, account_id: int, **kwargs: Any) -> ImportResult:
        from localledger.ingestion.importer import import_csv

        return import_csv(conn, account_id=account_id, **kwargs)
