from datetime import date, timedelta

import pytest

from localledger.connectors.amounts import to_minor
from localledger.connectors.base import (
    ConnectorError,
    RemoteAccount,
    RemoteTransaction,
    SyncBatch,
)
from localledger.connectors.http import OutboundPolicy
from localledger.connectors.service import ConnectionService, list_connections
from localledger.security.secrets import connection_secret_name
from tests.conftest import TODAY, FakeConnector

CHECKING = RemoteAccount("acc-1", "Everyday Checking", "checking", "USD", "Fake Bank", "0001")


def tx(ext, amount, day=date(2026, 11, 3), desc="STARBUCKS COFFEE", **kw):
    return RemoteTransaction(ext, "acc-1", day, amount, desc, **kw)


@pytest.fixture
def service(db, secret_store, fake_bank):
    return ConnectionService(db, secret_store, {fake_bank.info.id: fake_bank})


def rows(db):
    with db.connect() as conn:
        return [tuple(r) for r in conn.execute(
            "SELECT external_id, amount_minor, is_pending, category FROM transactions"
            " ORDER BY external_id")]


def test_connect_stores_credentials_only_in_the_secret_store(service, db, secret_store):
    connection_id = service.connect("fakebank", {"token": "good"})
    assert secret_store.get(connection_secret_name(connection_id)) == {
        "access": "s3cr3t-access-value"}
    with db.connect() as conn:
        dump = "\n".join(str(tuple(r)) for t in ("connections", "accounts", "settings")
                         for r in conn.execute(f"SELECT * FROM {t}"))
    assert "s3cr3t" not in dump
    with pytest.raises(ConnectorError):
        service.connect("fakebank", {"token": "bad"})
    with pytest.raises(ConnectorError, match="not available"):
        service.connect("nope", {})


def test_sync_is_idempotent_and_uses_the_cursor(service, db, fake_bank):
    cid = service.connect("fakebank", {"token": "good"})
    batch = SyncBatch([CHECKING], [tx("t1", -575), tx("t2", 325000, desc="ACME PAYROLL")],
                      cursor="c1")
    fake_bank.batches = [batch, batch]
    first = service.sync(cid, TODAY)
    second = service.sync(cid, TODAY)
    assert (first.added, first.updated, first.accounts) == (2, 0, 1)
    assert (second.added, second.updated) == (0, 2)
    assert rows(db) == [("t1", -575, 0, "Restaurants"), ("t2", 325000, 0, "Income")]
    assert [c["cursor"] for c in fake_bank.sync_calls] == [None, "c1"]
    assert fake_bank.sync_calls[0]["since"] == TODAY - timedelta(days=90)
    with db.connect() as conn:
        listed = list_connections(conn)[0]
        account = conn.execute("SELECT name, connector, type FROM accounts").fetchone()
    assert (listed.status, listed.account_count, listed.transaction_count) == ("active", 1, 2)
    assert tuple(account) == ("Everyday Checking", "fakebank", "checking")


def test_pending_then_posted_modified_and_removed(service, db, fake_bank):
    cid = service.connect("fakebank", {"token": "good"})
    fake_bank.batches = [
        SyncBatch([CHECKING], [tx("p1", -2150, pending=True), tx("t9", -999), tx("gone", -1)]),
        SyncBatch([CHECKING], [tx("t1", -2300, replaces_external_id="p1"), tx("t9", -1099)],
                  removed_external_ids=["gone", "never-seen"]),
    ]
    service.sync(cid, TODAY)
    result = service.sync(cid, TODAY)
    assert (result.added, result.updated, result.removed) == (1, 1, 2)
    assert rows(db) == [("t1", -2300, 0, "Restaurants"), ("t9", -1099, 0, "Restaurants")]


def test_two_connections_with_the_same_remote_ids_do_not_collide(service, db, fake_bank):
    a = service.connect("fakebank", {"token": "good"})
    b = service.connect("fakebank", {"token": "good"})
    fake_bank.batches = [SyncBatch([CHECKING], [tx("t1", -100)]),
                         SyncBatch([CHECKING], [tx("t1", -200)])]
    service.sync(a, TODAY)
    service.sync(b, TODAY)
    with db.connect() as conn:
        names = [r["name"] for r in conn.execute("SELECT name FROM accounts ORDER BY id")]
    assert names == ["Everyday Checking", "Everyday Checking ••0001"]
    assert [r[1] for r in rows(db)] == [-100, -200]


def test_failures_are_recorded_and_need_attention_is_distinguished(service, db, fake_bank):
    cid = service.connect("fakebank", {"token": "good"})
    fake_bank.batches = [ConnectorError("access_revoked", "Reconnect.", needs_attention=True)]
    with pytest.raises(ConnectorError):
        service.sync(cid, TODAY)
    with db.connect() as conn:
        assert (list_connections(conn)[0].status,
                list_connections(conn)[0].last_error) == ("needs_attention", "Reconnect.")
    fake_bank.batches = [SyncBatch([CHECKING], [tx("t1", -100)])]
    service.sync(cid, TODAY)
    with db.connect() as conn:
        assert (list_connections(conn)[0].status,
                list_connections(conn)[0].last_error) == ("active", None)


def test_missing_keychain_item_asks_for_reconnect(service, secret_store, fake_bank):
    cid = service.connect("fakebank", {"token": "good"})
    secret_store.delete(connection_secret_name(cid))
    with pytest.raises(ConnectorError, match="Reconnect"):
        service.sync(cid, TODAY)
    assert fake_bank.sync_calls == []


def test_rate_limit_is_enforced_locally(db, secret_store):
    bank = FakeConnector(interval=3600)
    service = ConnectionService(db, secret_store, {"fakebank": bank})
    cid = service.connect("fakebank", {"token": "good"})
    service.sync(cid, TODAY)
    with pytest.raises(ConnectorError) as err:
        service.sync(cid, TODAY)
    assert err.value.code == "rate_limited" and len(bank.sync_calls) == 1


def test_disconnect_always_destroys_local_credentials(service, db, secret_store, fake_bank):
    keep = service.connect("fakebank", {"token": "good"})
    drop = service.connect("fakebank", {"token": "good"})
    fake_bank.batches = [SyncBatch([CHECKING], [tx("t1", -100)]),
                         SyncBatch([CHECKING], [tx("t1", -200)])]
    service.sync(keep, TODAY)
    service.sync(drop, TODAY)

    notes = service.disconnect(keep, delete_data=False)
    assert notes == ["Access revoked at Fake Bank."] and len(fake_bank.disconnected) == 1
    fake_bank.disconnect_error = ConnectorError("unreachable", "Could not reach the provider.")
    notes = service.disconnect(drop, delete_data=True)
    assert "could not be told to revoke" in notes[0]
    assert secret_store.items == {}
    with db.connect() as conn:
        assert list_connections(conn) == []
        left = [tuple(r) for r in conn.execute(
            "SELECT a.connection_id, t.amount_minor FROM accounts a"
            " JOIN transactions t ON t.account_id = a.id")]
    assert left == [(None, -100)]  # kept data is detached; deleted data is gone


def test_offline_disconnect_skips_the_provider_but_still_clears_credentials(
        service, secret_store, fake_bank):
    cid = service.connect("fakebank", {"token": "good"})
    notes = service.disconnect(cid, delete_data=True, offline=True)
    assert "not revoked at the provider" in notes[0]
    assert fake_bank.disconnected == [] and secret_store.items == {}


def test_bank_data_feeds_the_same_analytics(service, db, fake_bank):
    from localledger.analytics import core
    from localledger.analytics.periods import resolve_period

    cid = service.connect("fakebank", {"token": "good"})
    fake_bank.batches = [SyncBatch([CHECKING], [
        tx("a", -1250, date(2026, 10, 5)), tx("b", -2000, date(2026, 10, 9), "CHIPOTLE 0456"),
        tx("c", -40000, date(2026, 10, 16), "ONLINE TRANSFER TO SAVINGS")])]
    service.sync(cid, TODAY)
    with db.connect() as conn:
        spend = core.spending_by_category(conn, resolve_period("last_month", TODAY))
    assert spend["total_spending_minor"] == 3250  # the transfer is excluded


def test_amount_conversion_is_exact_and_rejects_floats():
    from decimal import Decimal
    assert to_minor("-33293.43") == -3329343
    assert to_minor(Decimal("1.15")) == 115
    assert to_minor("0.1") + to_minor("0.2") == 30
    assert to_minor(12) == 1200
    with pytest.raises(TypeError):
        to_minor(1.15)
    for bad in ("abc", "NaN", "1e40"):
        with pytest.raises(ConnectorError):
            to_minor(bad)


def test_outbound_policy_allows_only_declared_https_hosts():
    policy = OutboundPolicy(allowed_hosts=("sandbox.plaid.com",),
                            allowed_suffixes=("simplefin.org",))
    assert policy.check("https://sandbox.plaid.com/x")
    assert policy.check("https://user:pw@beta-bridge.simplefin.org/simplefin")
    for bad in ("http://sandbox.plaid.com/x", "https://production.plaid.com/x",
                "https://sandbox.plaid.com.evil.example/x", "https://evilsimplefin.org/x",
                "https://simplefin.org.evil.example/", "https://127.0.0.1/x", "file:///etc"):
        with pytest.raises(ConnectorError):
            policy.check(bad)
