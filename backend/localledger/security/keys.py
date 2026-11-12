"""Database key management via the OS credential store (macOS Keychain)."""

from __future__ import annotations

import contextlib
import secrets

import keyring

from localledger.config import app_namespace

_KEY_NAME = "database-key-v1"


def get_or_create_db_key(service: str | None = None) -> bytes:
    service = service or app_namespace()
    existing = keyring.get_password(service, _KEY_NAME)
    if existing:
        return bytes.fromhex(existing)
    key = secrets.token_bytes(32)
    keyring.set_password(service, _KEY_NAME, key.hex())
    return key


def delete_db_key(service: str | None = None) -> None:
    service = service or app_namespace()
    with contextlib.suppress(keyring.errors.PasswordDeleteError):
        keyring.delete_password(service, _KEY_NAME)
