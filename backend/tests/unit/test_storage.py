import secrets
import sqlite3

import pytest

from localledger.demo.loader import load_demo
from localledger.storage.db import Database, StorageError
from tests.conftest import TODAY


def test_database_file_is_encrypted_at_rest(tmp_path):
    key = secrets.token_bytes(32)
    db = Database(tmp_path / "ledger.db", key)
    db.migrate()
    with db.connect() as conn:
        load_demo(conn, TODAY)
    with db.connect() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
    raw = b"".join(p.read_bytes() for p in tmp_path.iterdir())
    assert not raw.startswith(b"SQLite format 3")
    for needle in (b"STARBUCKS", b"Starbucks", b"PAYROLL", b"transactions", b"Restaurants"):
        assert needle not in raw
    # The stock SQLite driver cannot read it at all.
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(tmp_path / "ledger.db").execute("SELECT * FROM sqlite_master").fetchall()


def test_wrong_key_is_rejected(tmp_path):
    Database(tmp_path / "ledger.db", secrets.token_bytes(32)).migrate()
    other = Database(tmp_path / "ledger.db", secrets.token_bytes(32))
    with pytest.raises(StorageError), other.connect():
        pass


def test_key_is_mandatory_unless_insecure_mode_is_explicit(tmp_path):
    with pytest.raises(StorageError):
        Database(tmp_path / "a.db", None)
    with pytest.raises(StorageError):
        Database(tmp_path / "a.db", b"short")
    dev = Database(tmp_path / "dev.sqlite", None, insecure=True)
    dev.migrate()
    assert dev.encrypted is False


def test_file_permissions_are_owner_only(db):
    assert db.path.stat().st_mode & 0o777 == 0o600


def test_migrations_are_idempotent_and_delete_wipes_everything(loaded_db):
    loaded_db.migrate()
    loaded_db.delete_all_data()
    with loaded_db.connect() as conn:
        for table in ("transactions", "accounts", "imports", "settings"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
