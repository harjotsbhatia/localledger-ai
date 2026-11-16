"""Provider credentials (bank access tokens, API secrets) live only in the OS keychain.

Nothing in this module logs, returns to the API, or writes to the database. Each bank
connection gets one keychain item named after its numeric id, holding a small JSON object.
"""

from __future__ import annotations

import json
from typing import Protocol

import keyring
import keyring.errors

from localledger.config import app_namespace


class SecretStore(Protocol):
    def get(self, name: str) -> dict[str, str] | None: ...
    def set(self, name: str, value: dict[str, str]) -> None: ...
    def delete(self, name: str) -> None: ...


class KeychainSecretStore:
    def __init__(self, service: str | None = None) -> None:
        self._service = service or app_namespace()

    def get(self, name: str) -> dict[str, str] | None:
        raw = keyring.get_password(self._service, name)
        return json.loads(raw) if raw else None

    def set(self, name: str, value: dict[str, str]) -> None:
        keyring.set_password(self._service, name, json.dumps(value))

    def delete(self, name: str) -> None:
        try:
            keyring.delete_password(self._service, name)
        except keyring.errors.PasswordDeleteError:
            return


class MemorySecretStore:
    """For tests and the OpenAPI export. Never used by the running app."""

    def __init__(self) -> None:
        self.items: dict[str, dict[str, str]] = {}

    def get(self, name: str) -> dict[str, str] | None:
        return self.items.get(name)

    def set(self, name: str, value: dict[str, str]) -> None:
        self.items[name] = dict(value)

    def delete(self, name: str) -> None:
        self.items.pop(name, None)


def connection_secret_name(connection_id: int) -> str:
    return f"connection-{connection_id}"
