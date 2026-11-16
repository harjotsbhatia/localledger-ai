"""SimpleFIN Bridge connector (read-only).

Flow, per https://www.simplefin.org/protocol.html (protocol 2.0 draft, v1 tolerated):
1. The user creates a setup token at the Bridge and pastes it here.
2. The token is a Base64 URL; one POST to it returns an Access URL with Basic credentials.
3. GET {access}/accounts returns accounts and transactions.

The user's bank password never reaches this app. Their transactions do pass through the
SimpleFIN Bridge and whichever aggregator it uses; the UI says so before connecting.
"""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from localledger.connectors.amounts import to_minor
from localledger.connectors.base import (
    ConnectorError,
    NewConnection,
    ProviderInfo,
    RemoteAccount,
    RemoteTransaction,
    SyncBatch,
)
from localledger.connectors.http import OutboundPolicy, new_client, request
from localledger.ingestion.normalize import clean_text

MAX_WINDOW_DAYS = 90
_REVOKE_NOTE = ("SimpleFIN access can only be revoked from the Bridge website. To fully "
                "disconnect, open your SimpleFIN Bridge account and disable this app's token.")


class SimpleFinConnector:
    info = ProviderInfo(
        id="simplefin",
        display_name="SimpleFIN Bridge",
        description="Read-only access to accounts and transactions through a token you "
                    "create at the SimpleFIN Bridge.",
        data_path="Your bank data passes through the SimpleFIN Bridge and its data partner "
                  "before reaching this Mac. Your bank password is never given to LocalLedger.",
        environment="live",
        fields=[{"name": "setup_token", "label": "Setup token", "secret": True,
                 "help": "Create one at bridge.simplefin.org. It can be used once."}],
        # The Bridge asks for 24 or fewer requests a day and disables tokens beyond that.
        min_sync_interval_seconds=3600,
    )

    def __init__(self, transport: httpx.BaseTransport | None = None,
                 policy: OutboundPolicy | None = None) -> None:
        self._transport = transport
        self._policy = policy or OutboundPolicy(allowed_suffixes=("simplefin.org",))

    def connect(self, params: dict[str, str]) -> NewConnection:
        token = "".join((params.get("setup_token") or "").split())
        try:
            claim_url = base64.b64decode(token, validate=True).decode("ascii").strip()
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise ConnectorError("invalid_token",
                                 "That does not look like a SimpleFIN setup token.") from exc
        self._policy.check(claim_url)
        with new_client(self._transport) as client:
            response = request(client, "POST", claim_url, headers={"Content-Length": "0"})
        if response.status_code == 403:
            raise ConnectorError(
                "token_rejected",
                "The Bridge rejected this token. It may already have been used. If you did "
                "not use it yourself, disable it at the Bridge, because someone else may "
                "have claimed it.")
        if response.status_code != 200:
            raise ConnectorError("claim_failed",
                                 f"The Bridge could not claim the token (HTTP "
                                 f"{response.status_code}).")
        access_url = response.text.strip()
        self._split(access_url)  # validates scheme, host and credentials
        return NewConnection(label="SimpleFIN Bridge", secret={"access_url": access_url})

    def _split(self, access_url: str) -> tuple[str, tuple[str, str]]:
        self._policy.check(access_url)
        parts = urlsplit(access_url)
        if not parts.username or parts.password is None:
            raise ConnectorError("bad_access_url", "The Bridge returned unusable credentials.")
        host = parts.hostname or ""
        netloc = f"{host}:{parts.port}" if parts.port else host
        base = urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))
        return base, (parts.username, parts.password)

    def sync(self, secret: dict[str, str], cursor: str | None, since: date,
             today: date) -> SyncBatch:
        base, auth = self._split(secret["access_url"])
        since = max(since, today - timedelta(days=MAX_WINDOW_DAYS))
        start = int(datetime.combine(since, time.min, tzinfo=UTC).timestamp())
        with new_client(self._transport) as client:
            response = request(client, "GET", f"{base}/accounts", auth=auth,
                               params={"version": "2", "start-date": str(start),
                                       "pending": "1"})
        if response.status_code == 403:
            raise ConnectorError(
                "access_revoked",
                "The Bridge refused these credentials. Access may have been revoked. "
                "Create a new setup token and reconnect.", needs_attention=True)
        if response.status_code == 402:
            raise ConnectorError("payment_required",
                                 "The Bridge reports that your SimpleFIN subscription needs "
                                 "attention.", needs_attention=True)
        if response.status_code != 200:
            raise ConnectorError("sync_failed",
                                 f"The Bridge returned HTTP {response.status_code}.")
        try:
            body = json.loads(response.text, parse_float=Decimal)
            accounts_json = body["accounts"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ConnectorError("bad_response",
                                 "The Bridge sent a response this app cannot read.") from exc

        institutions = {c.get("conn_id"): c.get("name") or c.get("org_name") or ""
                        for c in body.get("connections") or [] if isinstance(c, dict)}
        batch = SyncBatch(messages=_messages(body))
        for account in accounts_json:
            account_id = str(account["id"])
            org = account.get("org") if isinstance(account.get("org"), dict) else {}
            batch.accounts.append(RemoteAccount(
                external_id=account_id,
                name=str(account.get("name") or "Account"),
                currency=str(account.get("currency") or "USD"),
                institution=str(institutions.get(account.get("conn_id"))
                                or org.get("name") or org.get("domain") or ""),
            ))
            for tx in account.get("transactions") or []:
                pending = bool(tx.get("pending")) or not tx.get("posted")
                stamp = tx.get("posted") or tx.get("transacted_at")
                day = datetime.fromtimestamp(int(stamp), UTC).date() if stamp else today
                batch.upserts.append(RemoteTransaction(
                    external_id=f"{account_id}:{tx['id']}",  # ids are unique per account
                    account_external_id=account_id,
                    posted_date=day,
                    amount_minor=to_minor(tx["amount"]),  # positive = deposit, as we store
                    description=str(tx.get("description") or tx.get("payee") or "Unknown"),
                    pending=pending,
                ))
        return batch

    def disconnect(self, secret: dict[str, str]) -> str | None:
        return _REVOKE_NOTE


def _messages(body: dict[str, Any]) -> list[str]:
    """Bridge errors are meant for the user, except developer-facing `gen.api` notices."""
    out: list[str] = []
    for err in body.get("errlist") or []:
        if isinstance(err, dict) and err.get("msg") and err.get("code") != "gen.api":
            out.append(clean_text(str(err["msg"]), 300))
    if not out:
        out = [clean_text(str(m), 300) for m in body.get("errors") or [] if isinstance(m, str)]
    return out
