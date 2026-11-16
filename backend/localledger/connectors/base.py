"""Common contract for bank connectors.

A connector turns a provider's API into provider-neutral accounts and transactions.
Everything downstream (storage, analytics, the assistant) sees only normalized rows, so
adding or replacing a provider touches nothing outside this package.

Conventions every connector must follow:
- amounts are integer minor units with LocalLedger's sign: negative = money out;
- `external_id` is the provider's stable id, used for idempotent upserts;
- credentials are returned to the caller as a `secret` dict and stored only in the keychain;
- access is read-only. A connector never moves money or changes anything at the bank.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from pydantic import BaseModel


class ConnectorError(Exception):
    """A failure that is safe to show to the user. Never include credentials in `message`."""

    def __init__(self, code: str, message: str, *, needs_attention: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.needs_attention = needs_attention


@dataclass
class RemoteAccount:
    external_id: str
    name: str
    type: str = "other"  # checking | savings | credit_card | other
    currency: str = "USD"
    institution: str = ""
    mask: str = ""


@dataclass
class RemoteTransaction:
    external_id: str
    account_external_id: str
    posted_date: date
    amount_minor: int
    description: str
    pending: bool = False
    replaces_external_id: str | None = None
    """Id of the pending transaction this posted one supersedes, if the provider says so."""


@dataclass
class SyncBatch:
    accounts: list[RemoteAccount] = field(default_factory=list)
    upserts: list[RemoteTransaction] = field(default_factory=list)
    removed_external_ids: list[str] = field(default_factory=list)
    cursor: str | None = None
    messages: list[str] = field(default_factory=list)
    """Provider notices for the user. Already sanitized by the connector."""


@dataclass
class NewConnection:
    label: str
    secret: dict[str, str]


class FieldOption(BaseModel):
    value: str
    label: str


class ProviderField(BaseModel):
    name: str
    label: str
    secret: bool = False
    help: str = ""
    options: list[FieldOption] = []


class ProviderInfo(BaseModel):
    id: str
    display_name: str
    description: str
    data_path: str
    """Plain statement of which third party sees the user's data."""
    environment: str
    fields: list[ProviderField]
    min_sync_interval_seconds: int


class BankConnector(Protocol):
    info: ProviderInfo

    def connect(self, params: dict[str, str]) -> NewConnection:
        """Exchange user-supplied setup values for long-lived credentials."""

    def sync(self, secret: dict[str, str], cursor: str | None, since: date,
             today: date) -> SyncBatch:
        """Fetch accounts and transactions changed since `cursor` (or `since`)."""

    def disconnect(self, secret: dict[str, str]) -> str | None:
        """Revoke access at the provider where possible. Returns a note for the user."""
