from __future__ import annotations

import secrets
from datetime import date
from typing import Any

import pytest

from localledger.demo.generator import generate
from localledger.demo.loader import load_demo
from localledger.llm.base import ChatResponse, LLMUnavailable, ModelInfo
from localledger.storage.db import Database

TODAY = date(2026, 11, 10)


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

