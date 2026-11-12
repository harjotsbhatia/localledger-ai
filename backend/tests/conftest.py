from __future__ import annotations

import secrets
from datetime import date

import pytest

from localledger.demo.generator import generate
from localledger.demo.loader import load_demo
from localledger.storage.db import Database

TODAY = date(2026, 11, 10)


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
