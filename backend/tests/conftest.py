from __future__ import annotations

import secrets
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from localledger.api.app import create_app
from localledger.config import Config
from localledger.connectors.base import (
    ConnectorError,
    NewConnection,
    ProviderInfo,
    SyncBatch,
)
from localledger.demo.generator import generate
from localledger.demo.loader import load_demo
from localledger.llm.base import ChatResponse, LLMUnavailable, ModelInfo
from localledger.security.secrets import MemorySecretStore
from localledger.storage.db import Database

TODAY = date(2026, 11, 10)
TOKEN = "t" * 43


class ScriptedProvider:
    """Deterministic stand-in for a local model: replays prepared responses."""

    def __init__(self, responses: list[ChatResponse] | None = None, *, down: bool = False):
        self.responses = list(responses or [])
        self.down = down
        self.calls: list[list[dict[str, Any]]] = []

    def health(self) -> dict[str, Any]:
        if self.down:
            raise LLMUnavailable("Ollama is not reachable. Is it running?")
        return {"version": "test"}

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo("scripted:latest", 1, "0B")]

    def chat(self, model, messages, tools=None) -> ChatResponse:
        if self.down:
            raise LLMUnavailable("Ollama is not reachable. Is it running?")
        self.calls.append([dict(m) for m in messages])
        if not self.responses:
            return ChatResponse(content="")
        return self.responses.pop(0)


class FakeConnector:
    """A bank provider that replays prepared batches and records what it was given."""

    def __init__(self, provider: str = "fakebank", interval: int = 0) -> None:
        self.info = ProviderInfo(
            id=provider, display_name="Fake Bank", description="test", data_path="test",
            environment="test", fields=[], min_sync_interval_seconds=interval)
        self.batches: list[SyncBatch | ConnectorError] = []
        self.sync_calls: list[dict[str, Any]] = []
        self.disconnected: list[dict[str, str]] = []
        self.disconnect_error: ConnectorError | None = None

    def connect(self, params: dict[str, str]) -> NewConnection:
        if params.get("token") != "good":
            raise ConnectorError("invalid_token", "Bad token.")
        return NewConnection(label="Fake Bank", secret={"access": "s3cr3t-access-value"})

    def sync(self, secret, cursor, since, today) -> SyncBatch:
        self.sync_calls.append({"secret": dict(secret), "cursor": cursor, "since": since})
        item = self.batches.pop(0) if self.batches else SyncBatch(cursor=cursor)
        if isinstance(item, ConnectorError):
            raise item
        return item

    def disconnect(self, secret) -> str | None:
        if self.disconnect_error:
            raise self.disconnect_error
        self.disconnected.append(dict(secret))
        return "Access revoked at Fake Bank."


@pytest.fixture
def secret_store() -> MemorySecretStore:
    return MemorySecretStore()


@pytest.fixture
def fake_bank() -> FakeConnector:
    return FakeConnector()


@pytest.fixture
def db(tmp_path) -> Database:
    database = Database(tmp_path / "ledger.db", secrets.token_bytes(32))
    database.migrate()
    return database


@pytest.fixture(scope="session")
def dataset():
    return generate(TODAY)


@pytest.fixture
def loaded_db(db) -> Database:
    with db.connect() as conn:
        load_demo(conn, TODAY)
    return db


@pytest.fixture
def conn(loaded_db):
    with loaded_db.connect() as connection:
        yield connection


@pytest.fixture
def provider() -> ScriptedProvider:
    return ScriptedProvider()


@pytest.fixture
def client(db, tmp_path, provider, secret_store, fake_bank) -> TestClient:
    config = Config(data_dir=tmp_path, api_token=TOKEN,
                    allowed_origins=("tauri://localhost",))
    app = create_app(config, db, clock=lambda: TODAY, provider_factory=lambda url: provider,
                     secrets=secret_store, connectors={fake_bank.info.id: fake_bank})
    return TestClient(app, base_url="http://127.0.0.1:8765",
                      headers={"Authorization": f"Bearer {TOKEN}"})
