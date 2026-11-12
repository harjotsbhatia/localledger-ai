from fastapi.testclient import TestClient

from localledger.llm.base import ChatResponse, ToolCall
from tests.conftest import TOKEN

EVIL = "https://evil.example"


def test_requests_without_valid_token_are_rejected(client):
    anonymous = TestClient(client.app, base_url="http://127.0.0.1:8765")
    assert anonymous.get("/api/health").status_code == 401
    assert anonymous.get("/api/transactions").status_code == 401
    assert anonymous.get("/api/health",
                         headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert anonymous.get("/api/health", headers={"Authorization": TOKEN}).status_code == 401
    assert anonymous.post("/api/data/delete", json={"confirm": "DELETE"}).status_code == 401


def test_dns_rebinding_host_is_rejected_even_with_token(client):
    for host in ("evil.example", "127.0.0.1.evil.example", "0.0.0.0:8765"):
        response = client.get("/api/health", headers={"Host": host})
        assert response.status_code == 403, host
    assert client.get("/api/health", headers={"Host": "localhost:8765"}).status_code == 200


def test_cross_origin_requests_get_no_cors_grant(client):
    preflight = client.options("/api/chat", headers={
        "Origin": EVIL, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    simple = client.get("/api/health", headers={"Origin": EVIL})
    assert "access-control-allow-origin" not in simple.headers

    ok = client.options("/api/chat", headers={
        "Origin": "tauri://localhost", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type"})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == "tauri://localhost"
    assert "access-control-allow-credentials" not in ok.headers


def test_docs_and_schema_are_not_served(client):
    for path in ("/docs", "/openapi.json", "/redoc"):
        assert client.get(path).status_code == 404


def test_health_reports_encryption(client):
    body = client.get("/api/health").json()
    assert body["storage_encrypted"] is True and body["storage_mode"] == "sqlcipher"


def test_full_import_dashboard_and_chat_flow(client, provider, dataset):
    golden = dataset.golden
    # 1. create an account and import a statement through preview -> mapping -> import
    account = client.post("/api/accounts", json={"name": "Everyday Checking"}).json()
    content = dataset.files["everyday_checking.csv"]
    preview = client.post("/api/imports/preview", json={"content": content}).json()
    assert preview["row_count"] == golden["transactions_by_account"]["Everyday Checking"]
    body = {"account_id": account["id"], "filename": "everyday_checking.csv",
            "content": content, "mapping": preview["suggested_mapping"]}
    first = client.post("/api/imports", json=body).json()
    assert first["rows_inserted"] == preview["row_count"] and first["rows_invalid"] == 0
    assert client.post("/api/imports", json=body).json()["rows_inserted"] == 0
    # 2. the demo loader tops up the second account without duplicating the first
    demo = client.post("/api/demo/load").json()
    assert demo["rows_inserted"] == golden["transactions_by_account"]["Rewards Credit Card"]
    assert demo["rows_duplicate"] == preview["row_count"]

    # 3. dashboard numbers come from the database and match the golden answers
    overview = client.get("/api/analytics/overview", params={"period": "last_month"}).json()
    october = golden["months"]["2026-10"]
    assert overview["cash_flow"]["spending_minor"] == october["spending_minor"]
    assert overview["cash_flow"]["income_minor"] == october["income_minor"]
    assert {c["category"]: c["total_minor"] for c in overview["categories"]} == october[
        "by_category_minor"]
    assert [p["month"] for p in overview["trend"]] == sorted(golden["months"])[-13:]
    page = client.get("/api/transactions", params={"category": "Restaurants",
                                                   "period": "last_month", "limit": 200}).json()
    assert -page["net_amount_minor"] == golden["restaurants_last_month_minor"]
    assert client.get("/api/analytics/recurring").json()[0]["cadence"] == "monthly"

    # 4. chat needs a configured model, then answers through the validated tool
    question = {"messages": [{"role": "user",
                              "content": "How much did I spend on restaurants last month?"}]}
    assert client.post("/api/chat", json=question).json()["detail"]["code"] == "no_model"
    client.put("/api/settings", json={"model": "scripted:latest"})
    amount = golden["restaurants_last_month_minor"]
    provider.responses = [
        ChatResponse(content="", tool_calls=[ToolCall(
            "get_spending_by_category", {"period": "last_month", "category": "Restaurants"})]),
        ChatResponse(content=f"You spent ${amount / 100:,.2f} on restaurants last month."),
    ]
    answer = client.post("/api/chat", json=question).json()
    assert answer["grounded"] is True
    assert answer["tool_calls"][0]["result"]["total_spending_minor"] == amount


def test_chat_reports_unavailable_model_cleanly(client, provider):
    client.put("/api/settings", json={"model": "scripted:latest"})
    provider.down = True
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "llm_unavailable"
    status = client.get("/api/ollama/status").json()
    assert status["reachable"] is False and status["models"] == []


def test_settings_validation_and_offline_mode(client):
    bad = client.put("/api/settings", json={"ollama_url": "https://api.example.com"})
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "invalid_url"
    assert client.put("/api/settings", json={"offline_mode": True}).json()["offline_mode"]
    blocked = client.post("/api/ollama/pull", json={"model": "llama3.2:3b"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "offline_mode"
    assert client.post("/api/ollama/pull", json={"model": "x; rm -rf /"}).status_code == 422


def test_invalid_inputs_are_rejected(client):
    assert client.get("/api/transactions", params={"category": "Nope"}).status_code == 400
    assert client.get("/api/analytics/overview", params={"period": "zzz"}).status_code == 400
    assert client.post("/api/imports/preview", json={"content": "x"}).status_code == 400
    assert client.post("/api/accounts", json={"name": ""}).status_code == 422
    assert client.delete("/api/accounts/999").status_code == 404


def test_delete_account_and_delete_all_data(client):
    client.post("/api/demo/load")
    accounts = client.get("/api/accounts").json()
    assert len(accounts) == 2
    assert client.delete(f"/api/accounts/{accounts[0]['id']}").status_code == 204
    remaining = client.get("/api/transactions").json()
    assert {t["account_id"] for t in remaining["transactions"]} == {accounts[1]["id"]}
    assert client.post("/api/data/delete", json={"confirm": "yes"}).status_code == 422
    assert client.post("/api/data/delete", json={"confirm": "DELETE"}).status_code == 204
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/transactions").json()["total_count"] == 0
