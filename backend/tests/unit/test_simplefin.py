import base64
import json
from datetime import UTC, date, datetime

import httpx
import pytest

from localledger.connectors.base import ConnectorError
from localledger.connectors.simplefin import SimpleFinConnector
from tests.conftest import TODAY

CLAIM = "https://bridge.simplefin.org/simplefin/claim/abc"
ACCESS = "https://user1:pw-secret@bridge.simplefin.org/simplefin"
TOKEN = base64.b64encode(CLAIM.encode()).decode()


def epoch(y, m, d):
    return int(datetime(y, m, d, 12, tzinfo=UTC).timestamp())


ACCOUNTS = {
    "errlist": [{"code": "con.auth", "msg": "Reconnect <b>My Bank</b>\x07 soon", "conn_id": "c1"},
                {"code": "gen.api", "msg": "developer notice"}],
    "connections": [{"conn_id": "c1", "name": "My Bank", "org_id": "o", "sfin_url": "x"}],
    "accounts": [{
        "id": "ACT-1", "name": "Savings", "conn_id": "c1", "currency": "USD",
        "balance": "100.23", "balance-date": epoch(2026, 11, 9),
        "transactions": [
            {"id": "T1", "posted": epoch(2026, 11, 3), "amount": "-33293.43",
             "description": "RENT PAYMENT OAKWOOD"},
            {"id": "T2", "posted": epoch(2026, 11, 4), "amount": "0.10",
             "description": "INTEREST PAID"},
            {"id": "T3", "posted": 0, "transacted_at": epoch(2026, 11, 8), "amount": "-4.50",
             "description": "BLUE BOTTLE CAFE", "pending": True},
        ],
    }],
}


def make(handler):
    seen: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return SimpleFinConnector(transport=httpx.MockTransport(wrapped)), seen


def test_claim_exchanges_the_setup_token_for_an_access_url():
    connector, seen = make(lambda r: httpx.Response(200, text=ACCESS + "\n"))
    new = connector.connect({"setup_token": f"  {TOKEN[:20]}\n{TOKEN[20:]} "})
    assert new.secret == {"access_url": ACCESS}
    assert (seen[0].method, str(seen[0].url), seen[0].content) == ("POST", CLAIM, b"")


@pytest.mark.parametrize(("token", "code"), [
    ("not base64 !!", "invalid_token"),
    (base64.b64encode(b"http://bridge.simplefin.org/claim/x").decode(), "insecure_url"),
    (base64.b64encode(b"https://evil.example/claim/x").decode(), "host_not_allowed"),
])
def test_bad_tokens_never_reach_the_network(token, code):
    connector, seen = make(lambda r: httpx.Response(200, text=ACCESS))
    with pytest.raises(ConnectorError) as err:
        connector.connect({"setup_token": token})
    assert err.value.code == code and seen == []


def test_claim_failures_and_hostile_access_urls():
    connector, _ = make(lambda r: httpx.Response(403))
    with pytest.raises(ConnectorError, match="someone else may have claimed"):
        connector.connect({"setup_token": TOKEN})
    for body in ("https://u:p@evil.example/simplefin", "http://u:p@bridge.simplefin.org/x",
                 "https://bridge.simplefin.org/no-credentials"):
        connector, _ = make(lambda r, b=body: httpx.Response(200, text=b))
        with pytest.raises(ConnectorError):
            connector.connect({"setup_token": TOKEN})


def test_sync_parses_accounts_transactions_and_notices():
    connector, seen = make(lambda r: httpx.Response(200, text=json.dumps(ACCOUNTS)))
    batch = connector.sync({"access_url": ACCESS}, None, date(2026, 10, 1), TODAY)
    request = seen[0]
    assert request.url.host == "bridge.simplefin.org"
    assert request.url.path == "/simplefin/accounts"
    assert request.url.userinfo == b""  # credentials go in the header, not the URL
    assert request.headers["authorization"].startswith("Basic ")
    assert dict(request.url.params) == {
        "version": "2", "pending": "1",
        "start-date": str(int(datetime(2026, 10, 1, tzinfo=UTC).timestamp()))}
    account = batch.accounts[0]
    assert (account.external_id, account.name, account.institution) == (
        "ACT-1", "Savings", "My Bank")
    got = [(t.external_id, t.posted_date, t.amount_minor, t.pending) for t in batch.upserts]
    assert got == [("ACT-1:T1", date(2026, 11, 3), -3329343, False),
                   ("ACT-1:T2", date(2026, 11, 4), 10, False),
                   ("ACT-1:T3", date(2026, 11, 8), -450, True)]
    assert batch.messages == ["Reconnect <b>My Bank</b> soon"]  # control chars stripped


def test_sync_never_asks_for_more_than_ninety_days():
    connector, seen = make(lambda r: httpx.Response(200, text='{"accounts": []}'))
    connector.sync({"access_url": ACCESS}, None, date(2020, 1, 1), TODAY)
    start = int(seen[0].url.params["start-date"])
    assert datetime.fromtimestamp(start, UTC).date() == date(2026, 8, 12)


def test_version_one_responses_are_still_understood():
    body = {"errors": ["Bank is slow today"], "accounts": [{
        "id": "A", "name": "Chk", "currency": "USD", "org": {"name": "Old Org"},
        "transactions": [{"id": "1", "posted": epoch(2026, 11, 1), "amount": "5.00",
                          "description": "DEPOSIT"}]}]}
    connector, _ = make(lambda r: httpx.Response(200, text=json.dumps(body)))
    batch = connector.sync({"access_url": ACCESS}, None, TODAY, TODAY)
    assert batch.accounts[0].institution == "Old Org" and batch.messages == ["Bank is slow today"]


@pytest.mark.parametrize(("status", "body", "code", "attention"), [
    (403, "", "access_revoked", True), (402, "", "payment_required", True),
    (500, "", "sync_failed", False), (200, "<html>", "bad_response", False),
    (200, '{"accounts": [{"id": "A", "transactions": [{"id": "1", "amount": "x"}]}]}',
     "bad_amount", False),
])
def test_sync_errors(status, body, code, attention):
    connector, _ = make(lambda r: httpx.Response(status, text=body))
    with pytest.raises(ConnectorError) as err:
        connector.sync({"access_url": ACCESS}, None, TODAY, TODAY)
    assert (err.value.code, err.value.needs_attention) == (code, attention)
    assert "pw-secret" not in err.value.message


def test_network_failure_is_reported_without_credentials():
    def boom(request):
        raise httpx.ConnectError("dns failure for " + str(request.url))

    connector, _ = make(boom)
    with pytest.raises(ConnectorError) as err:
        connector.sync({"access_url": ACCESS}, None, TODAY, TODAY)
    assert err.value.code == "unreachable" and "pw-secret" not in err.value.message


def test_disconnect_explains_that_revocation_happens_at_the_bridge():
    connector, seen = make(lambda r: httpx.Response(200))
    assert "Bridge website" in connector.disconnect({"access_url": ACCESS})
    assert seen == []
