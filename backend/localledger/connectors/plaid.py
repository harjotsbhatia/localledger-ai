"""Plaid connector, SANDBOX ONLY.

This talks exclusively to https://sandbox.plaid.com, which serves fabricated test data.
Items are created with the Sandbox-only /sandbox/public_token/create endpoint, so no Plaid
Link widget (and no third-party JavaScript) is loaded into the app.

There is intentionally no production mode. Production requires Plaid Link, Plaid's approval,
and an answer to whether a desktop app may hold a user's own client secret under Plaid's
developer policy. See SECURITY.md before changing PLAID_HOST.
"""

from __future__ import annotations

import json
import time as _time
from collections.abc import Callable
from datetime import date
from decimal import Decimal
from typing import Any

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

PLAID_HOST = "sandbox.plaid.com"
SANDBOX_INSTITUTIONS = {
    "ins_109508": "First Platypus Bank",
    "ins_109509": "First Gingham Credit Union",
    "ins_109510": "Tattersall Federal Credit Union",
    "ins_109511": "Tartan Bank",
    "ins_109512": "Houndstooth Bank",
}
_PAGE_SIZE = 500
_MAX_PAGES = 40
_MAX_RESTARTS = 3
_READY_ATTEMPTS = 6


def _account_type(kind: str | None, subtype: str | None) -> str:
    if kind == "credit":
        return "credit_card"
    if kind == "depository":
        return "savings" if subtype in {"savings", "money market", "cd"} else "checking"
    return "other"


class PlaidSandboxConnector:
    info = ProviderInfo(
        id="plaid_sandbox",
        display_name="Plaid (Sandbox test data)",
        description="Connects to Plaid's Sandbox, which returns fabricated accounts and "
                    "transactions. For development and demonstration only; it cannot reach "
                    "a real bank.",
        data_path="Requests go to sandbox.plaid.com using your own Plaid Sandbox keys. The "
                  "data is synthetic.",
        environment="sandbox",
        fields=[
            {"name": "client_id", "label": "Plaid client ID", "secret": False,
             "help": "From the Plaid dashboard, under Developers → Keys."},
            {"name": "secret", "label": "Plaid Sandbox secret", "secret": True,
             "help": "Use the Sandbox secret only. Never enter a Production secret."},
            {"name": "institution_id", "label": "Test institution", "secret": False,
             "options": [{"value": k, "label": v} for k, v in SANDBOX_INSTITUTIONS.items()]},
        ],
        min_sync_interval_seconds=0,
    )

    def __init__(self, transport: httpx.BaseTransport | None = None,
                 sleep: Callable[[float], None] = _time.sleep) -> None:
        self._transport = transport
        self._sleep = sleep
        self._policy = OutboundPolicy(allowed_hosts=(PLAID_HOST,))

    def _post(self, client: httpx.Client, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self._policy.check(f"https://{PLAID_HOST}{path}")
        response = request(client, "POST", url, json=payload)
        try:
            body = json.loads(response.text, parse_float=Decimal)
        except ValueError as exc:
            raise ConnectorError("bad_response",
                                 "Plaid sent a response this app cannot read.") from exc
        if response.status_code != 200 or not isinstance(body, dict):
            raise _plaid_error(body if isinstance(body, dict) else {}, response.status_code)
        return body

    def connect(self, params: dict[str, str]) -> NewConnection:
        client_id = (params.get("client_id") or "").strip()
        secret = (params.get("secret") or "").strip()
        institution = (params.get("institution_id") or "").strip()
        if not client_id or not secret:
            raise ConnectorError("missing_keys", "Enter your Plaid client ID and Sandbox secret.")
        if institution not in SANDBOX_INSTITUTIONS:
            raise ConnectorError("unknown_institution", "Choose one of the test institutions.")
        keys = {"client_id": client_id, "secret": secret}
        with new_client(self._transport) as client:
            created = self._post(client, "/sandbox/public_token/create", {
                **keys, "institution_id": institution, "initial_products": ["transactions"]})
            exchanged = self._post(client, "/item/public_token/exchange", {
                **keys, "public_token": created["public_token"]})
        return NewConnection(
            label=f"{SANDBOX_INSTITUTIONS[institution]} (Plaid Sandbox)",
            secret={**keys, "access_token": str(exchanged["access_token"]),
                    "item_id": str(exchanged.get("item_id", ""))},
        )

    def sync(self, secret: dict[str, str], cursor: str | None, since: date,
             today: date) -> SyncBatch:
        auth = {k: secret[k] for k in ("client_id", "secret", "access_token")}
        with new_client(self._transport) as client:
            for attempt in range(_READY_ATTEMPTS):
                batch, status = self._sync_once(client, auth, cursor)
                waiting = status == "NOT_READY" or (cursor is None and not batch.upserts)
                if not waiting or attempt == _READY_ATTEMPTS - 1:
                    break
                # A freshly created Item returns empty pages for a few seconds.
                self._sleep(2.0)
        if cursor is None and not batch.upserts:
            batch.messages.append("Plaid is still preparing this item's transactions. "
                                  "Sync again in a minute.")
            batch.cursor = None  # start from the beginning next time
        return batch

    def _sync_once(self, client: httpx.Client, auth: dict[str, str],
                   start_cursor: str | None) -> tuple[SyncBatch, str]:
        for _ in range(_MAX_RESTARTS):
            batch = SyncBatch(cursor=start_cursor)
            accounts: dict[str, RemoteAccount] = {}
            cursor, status = start_cursor, "UNKNOWN"
            try:
                for _page in range(_MAX_PAGES):
                    payload: dict[str, Any] = {**auth, "count": _PAGE_SIZE}
                    if cursor:
                        payload["cursor"] = cursor
                    body = self._post(client, "/transactions/sync", payload)
                    status = str(body.get("transactions_update_status") or status)
                    for account in body.get("accounts") or []:
                        accounts[account["account_id"]] = RemoteAccount(
                            external_id=account["account_id"],
                            name=str(account.get("name") or account.get("official_name")
                                     or "Account"),
                            type=_account_type(account.get("type"), account.get("subtype")),
                            currency=str((account.get("balances") or {}).get(
                                "iso_currency_code") or "USD"),
                            institution="Plaid Sandbox",
                            mask=str(account.get("mask") or ""),
                        )
                    for tx in [*(body.get("added") or []), *(body.get("modified") or [])]:
                        batch.upserts.append(_transaction(tx))
                    batch.removed_external_ids += [
                        str(r["transaction_id"]) for r in body.get("removed") or []]
                    cursor = body.get("next_cursor") or cursor
                    if not body.get("has_more"):
                        batch.accounts = list(accounts.values())
                        batch.cursor = cursor
                        return batch, status
            except ConnectorError as exc:
                # Plaid: if data changes mid-pagination, restart from the first cursor
                # rather than retrying the single failed page.
                if exc.code != "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION":
                    raise
                continue
            raise ConnectorError("too_many_pages", "Plaid returned more data than expected.")
        raise ConnectorError("sync_unstable",
                             "Plaid's data kept changing during sync. Try again shortly.")

    def disconnect(self, secret: dict[str, str]) -> str | None:
        with new_client(self._transport) as client:
            self._post(client, "/item/remove",
                       {k: secret[k] for k in ("client_id", "secret", "access_token")})
        return "The Plaid item was removed and its access token is no longer valid."


def _transaction(tx: dict[str, Any]) -> RemoteTransaction:
    raw_date = tx.get("date") or tx.get("authorized_date")
    return RemoteTransaction(
        external_id=str(tx["transaction_id"]),
        account_external_id=str(tx["account_id"]),
        posted_date=date.fromisoformat(str(raw_date)),
        # Plaid: positive = money leaving the account. LocalLedger stores the opposite.
        amount_minor=-to_minor(tx["amount"]),
        description=str(tx.get("merchant_name") or tx.get("name") or "Unknown"),
        pending=bool(tx.get("pending")),
        replaces_external_id=tx.get("pending_transaction_id") or None,
    )


def _plaid_error(body: dict[str, Any], status: int) -> ConnectorError:
    code = str(body.get("error_code") or f"HTTP_{status}")
    if code == "ITEM_LOGIN_REQUIRED":
        return ConnectorError(code, "This Plaid item needs to be reconnected.",
                              needs_attention=True)
    if code in {"INVALID_API_KEYS", "INVALID_SECRET", "INVALID_CLIENT_ID",
                "UNAUTHORIZED_ENVIRONMENT"}:
        return ConnectorError(code, "Plaid rejected these keys. Check the client ID and make "
                                    "sure you used the Sandbox secret.", needs_attention=True)
    if code == "INVALID_ACCESS_TOKEN":
        return ConnectorError(code, "Plaid no longer recognizes this connection. Reconnect it.",
                              needs_attention=True)
    # error_message is developer-facing and may echo request details, so it is not shown.
    display = body.get("display_message")
    return ConnectorError(code, str(display) if display else f"Plaid reported an error ({code}).")
