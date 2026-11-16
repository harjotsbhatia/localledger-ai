import logging
from datetime import date

from localledger.connectors.base import ConnectorError, RemoteAccount, RemoteTransaction, SyncBatch

SECRET_VALUE = "s3cr3t-access-value"
BATCH = SyncBatch(
    [RemoteAccount("acc-1", "Everyday Checking", "checking", "USD", "Fake Bank", "0001")],
    [RemoteTransaction("t1", "acc-1", date(2026, 10, 5), -1250, "STARBUCKS COFFEE"),
     RemoteTransaction("t2", "acc-1", date(2026, 10, 1), 325000, "ACME PAYROLL DIRECT DEP")],
    cursor="c1", messages=["Bank notice"])


def test_connect_sync_and_disconnect_flow(client, fake_bank, secret_store, caplog):
    caplog.set_level(logging.DEBUG)
    assert [p["id"] for p in client.get("/api/connections/providers").json()] == ["fakebank"]
    assert client.post("/api/connections", json={
        "provider": "fakebank", "params": {"token": "bad"}}).status_code == 400
    assert client.post("/api/connections", json={
        "provider": "nope", "params": {}}).status_code == 404

    fake_bank.batches = [BATCH]
    created = client.post("/api/connections", json={"provider": "fakebank",
                                                    "params": {"token": "good"}})
    assert created.status_code == 201
    assert created.json() == {"connection_id": 1, "accounts": 1, "added": 2, "updated": 0,
                              "removed": 0, "messages": ["Bank notice"]}

    listed = client.get("/api/connections").json()
    assert listed[0]["status"] == "active" and listed[0]["transaction_count"] == 2
    account = client.get("/api/accounts").json()[0]
    assert (account["connector"], account["transaction_count"]) == ("fakebank", 2)
    overview = client.get("/api/analytics/overview", params={"period": "last_month"}).json()
    assert overview["cash_flow"] == {**overview["cash_flow"], "income_minor": 325000,
                                     "spending_minor": 1250}

    again = client.post("/api/connections/1/sync").json()
    assert (again["added"], again["updated"]) == (0, 0)
    assert fake_bank.sync_calls[1]["cursor"] == "c1"
    assert client.post("/api/connections/99/sync").status_code == 404

    # The credential is in the secret store and nowhere a client or log reader can see it.
    assert secret_store.items == {"connection-1": {"access": SECRET_VALUE}}
    for path in ("/api/connections", "/api/accounts", "/api/settings",
                 "/api/connections/providers"):
        assert SECRET_VALUE not in client.get(path).text
    assert SECRET_VALUE not in created.text and SECRET_VALUE not in caplog.text
    assert "STARBUCKS" not in caplog.text.upper()

    gone = client.delete("/api/connections/1", params={"delete_data": True})
    assert gone.json() == {"notes": ["Access revoked at Fake Bank."]}
    assert secret_store.items == {} and client.get("/api/accounts").json() == []
    assert client.delete("/api/connections/1").status_code == 404


def test_first_sync_failure_keeps_the_connection_and_reports_why(client, fake_bank):
    fake_bank.batches = [ConnectorError("unreachable", "Could not reach the provider.")]
    created = client.post("/api/connections", json={"provider": "fakebank",
                                                    "params": {"token": "good"}})
    assert created.status_code == 201
    assert created.json()["messages"] == ["Could not reach the provider."]
    assert client.get("/api/connections").json()[0]["status"] == "error"


def test_sync_errors_map_to_http_statuses(client, fake_bank):
    client.post("/api/connections", json={"provider": "fakebank", "params": {"token": "good"}})
    fake_bank.batches = [ConnectorError("access_revoked", "Reconnect.", needs_attention=True),
                         ConnectorError("sync_failed", "Provider error.")]
    first = client.post("/api/connections/1/sync")
    assert (first.status_code, first.json()["detail"]["code"]) == (409, "access_revoked")
    assert client.get("/api/connections").json()[0]["status"] == "needs_attention"
    assert client.post("/api/connections/1/sync").status_code == 502


def test_offline_mode_blocks_all_provider_contact(client, fake_bank, secret_store):
    fake_bank.batches = [BATCH]
    client.post("/api/connections", json={"provider": "fakebank", "params": {"token": "good"}})
    client.put("/api/settings", json={"offline_mode": True})
    calls = len(fake_bank.sync_calls)
    for response in (client.post("/api/connections/1/sync"),
                     client.post("/api/connections", json={"provider": "fakebank",
                                                           "params": {"token": "good"}})):
        assert (response.status_code, response.json()["detail"]["code"]) == (409, "offline_mode")
    assert len(fake_bank.sync_calls) == calls
    # Analysis of already-synced data keeps working offline, and so does disconnecting.
    assert client.get("/api/transactions").json()["total_count"] == 2
    notes = client.delete("/api/connections/1").json()["notes"]
    assert "not revoked at the provider" in notes[0]
    assert fake_bank.disconnected == [] and secret_store.items == {}


def test_delete_all_data_also_clears_bank_credentials(client, fake_bank, secret_store):
    fake_bank.batches = [BATCH]
    client.post("/api/connections", json={"provider": "fakebank", "params": {"token": "good"}})
    assert secret_store.items
    assert client.post("/api/data/delete", json={"confirm": "DELETE"}).status_code == 204
    assert secret_store.items == {} and client.get("/api/connections").json() == []


def test_connection_routes_require_the_api_token(client):
    from fastapi.testclient import TestClient
    anonymous = TestClient(client.app, base_url="http://127.0.0.1:8765")
    assert anonymous.get("/api/connections").status_code == 401
    assert anonymous.post("/api/connections", json={"provider": "fakebank",
                                                    "params": {"token": "good"}}).status_code == 401
