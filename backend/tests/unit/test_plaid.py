import json
from datetime import date

import httpx
import pytest

from localledger.connectors.base import ConnectorError
from localledger.connectors.plaid import PlaidSandboxConnector
from tests.conftest import TODAY

KEYS = {"client_id": "cid", "secret": "sandbox-secret-value"}
SECRET = {**KEYS, "access_token": "access-sandbox-123", "item_id": "item-1"}
ACCOUNT = {"account_id": "A1", "name": "Plaid Checking", "official_name": "Gold Checking",
           "type": "depository", "subtype": "checking", "mask": "0000",
           "balances": {"current": 110.0, "iso_currency_code": "USD"}}
CARD = {"account_id": "A2", "name": "Plaid Credit Card", "type": "credit",
        "subtype": "credit card", "mask": "3333", "balances": {"iso_currency_code": "USD"}}


def txn(tid, amount, account="A1", **extra):
    return {"transaction_id": tid, "account_id": account, "amount": amount,
            "iso_currency_code": "USD", "date": "2026-11-03", "name": "Uber 063015 SF**POOL**",
            "merchant_name": "Uber", "pending": False, "pending_transaction_id": None, **extra}


def make(responses):
    seen: list[tuple[str, dict]] = []
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.path, json.loads(request.content)))
        assert request.url.host == "sandbox.plaid.com" and request.url.scheme == "https"
        status, body = queue.pop(0)
        return httpx.Response(status, text=json.dumps(body))

    connector = PlaidSandboxConnector(transport=httpx.MockTransport(handler),
                                      sleep=lambda s: None)
    return connector, seen


def page(added=(), modified=(), removed=(), cursor="c1", more=False, accounts=(ACCOUNT, CARD),
         status="HISTORICAL_UPDATE_COMPLETE"):
    return (200, {"added": list(added), "modified": list(modified), "removed": list(removed),
                  "next_cursor": cursor, "has_more": more, "accounts": list(accounts),
                  "transactions_update_status": status, "request_id": "r"})


def test_connect_creates_a_sandbox_item_without_link():
    connector, seen = make([(200, {"public_token": "public-sandbox-1", "request_id": "r"}),
                            (200, {"access_token": "access-sandbox-123", "item_id": "item-1"})])
    new = connector.connect({**KEYS, "institution_id": "ins_109508"})
    assert new.label == "First Platypus Bank (Plaid Sandbox)" and new.secret == SECRET
    assert seen == [
        ("/sandbox/public_token/create", {**KEYS, "institution_id": "ins_109508",
                                          "initial_products": ["transactions"]}),
        ("/item/public_token/exchange", {**KEYS, "public_token": "public-sandbox-1"}),
    ]


@pytest.mark.parametrize(("params", "code"), [
    ({"client_id": "", "secret": "x", "institution_id": "ins_109508"}, "missing_keys"),
    ({**KEYS, "institution_id": "ins_1"}, "unknown_institution"),
])
def test_connect_validates_before_calling_plaid(params, code):
    connector, seen = make([])
    with pytest.raises(ConnectorError) as err:
        connector.connect(params)
    assert err.value.code == code and seen == []


def test_there_is_no_way_to_point_the_connector_at_production():
    connector, _ = make([])
    assert connector.info.environment == "sandbox"
    with pytest.raises(ConnectorError):
        connector._policy.check("https://production.plaid.com/transactions/sync")


def test_sync_paginates_and_converts_signs_exactly():
    connector, seen = make([
        page(added=[txn("t1", 6.33), txn("t2", -4.22, name="INTEREST", merchant_name=None)],
             cursor="c1", more=True),
        page(added=[txn("t3", 1.15, account="A2", date="2026-11-05")], cursor="c2"),
    ])
    batch = connector.sync(SECRET, None, TODAY, TODAY)
    assert [(p, b.get("cursor"), b["count"]) for p, b in seen] == [
        ("/transactions/sync", None, 500), ("/transactions/sync", "c1", 500)]
    assert seen[0][1]["access_token"] == "access-sandbox-123"
    assert batch.cursor == "c2"
    got = [(t.external_id, t.account_external_id, t.amount_minor, t.description, t.posted_date)
           for t in batch.upserts]
    assert got == [("t1", "A1", -633, "Uber", date(2026, 11, 3)),      # money out is negative
                   ("t2", "A1", 422, "INTEREST", date(2026, 11, 3)),   # money in is positive
                   ("t3", "A2", -115, "Uber", date(2026, 11, 5))]      # 1.15 stays exact
    assert [(a.external_id, a.type, a.mask) for a in batch.accounts] == [
        ("A1", "checking", "0000"), ("A2", "credit_card", "3333")]


def test_incremental_sync_carries_modified_removed_and_pending_links():
    connector, seen = make([page(
        added=[txn("posted", 23.0, pending_transaction_id="pend")],
        modified=[txn("t1", 7.0)], removed=[{"transaction_id": "old", "account_id": "A1"}],
        cursor="c9")])
    batch = connector.sync(SECRET, "c5", TODAY, TODAY)
    assert seen[0][1]["cursor"] == "c5"
    assert [(t.external_id, t.replaces_external_id) for t in batch.upserts] == [
        ("posted", "pend"), ("t1", None)]
    assert batch.removed_external_ids == ["old"] and batch.cursor == "c9"


def test_mutation_during_pagination_restarts_from_the_first_cursor():
    mutation = (400, {"error_type": "TRANSACTIONS_ERROR",
                      "error_code": "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION",
                      "error_message": "x", "display_message": None})
    connector, seen = make([
        page(added=[txn("stale", 1.0)], cursor="c1", more=True), mutation,
        page(added=[txn("t1", 1.0)], cursor="c1", more=True),
        page(added=[txn("t2", 2.0)], cursor="c2"),
    ])
    batch = connector.sync(SECRET, "c0", TODAY, TODAY)
    assert [b.get("cursor") for _, b in seen] == ["c0", "c1", "c0", "c1"]
    assert [t.external_id for t in batch.upserts] == ["t1", "t2"]  # nothing from the stale pass


def test_a_new_item_is_polled_until_transactions_are_ready():
    not_ready = page(cursor="", status="NOT_READY")
    connector, seen = make([not_ready, not_ready, page(added=[txn("t1", 5.0)], cursor="c1")])
    batch = connector.sync(SECRET, None, TODAY, TODAY)
    assert len(seen) == 3 and len(batch.upserts) == 1 and batch.messages == []


def test_an_item_that_never_becomes_ready_reports_it_and_keeps_no_cursor():
    connector, seen = make([page(cursor="empty", status="NOT_READY")] * 6)
    batch = connector.sync(SECRET, None, TODAY, TODAY)
    assert len(seen) == 6 and batch.cursor is None
    assert "still preparing" in batch.messages[0]


@pytest.mark.parametrize(("code", "attention", "phrase"), [
    ("ITEM_LOGIN_REQUIRED", True, "reconnected"),
    ("INVALID_API_KEYS", True, "Sandbox secret"),
    ("INVALID_ACCESS_TOKEN", True, "Reconnect"),
    ("INTERNAL_SERVER_ERROR", False, "INTERNAL_SERVER_ERROR"),
])
def test_plaid_errors_are_mapped_without_leaking_details(code, attention, phrase):
    connector, _ = make([(400, {
        "error_type": "X", "error_code": code, "display_message": None,
        "error_message": "secret sandbox-secret-value was wrong"})])
    with pytest.raises(ConnectorError) as err:
        connector.sync(SECRET, "c1", TODAY, TODAY)
    assert err.value.needs_attention is attention and phrase in err.value.message
    assert "sandbox-secret-value" not in err.value.message


def test_disconnect_removes_the_item_at_plaid():
    connector, seen = make([(200, {"request_id": "r"})])
    note = connector.disconnect(SECRET)
    assert seen == [("/item/remove", {**KEYS, "access_token": "access-sandbox-123"})]
    assert "no longer valid" in note
