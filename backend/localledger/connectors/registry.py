"""The bank connectors this build ships with."""

from __future__ import annotations

from localledger.connectors.base import BankConnector
from localledger.connectors.plaid import PlaidSandboxConnector
from localledger.connectors.simplefin import SimpleFinConnector


def default_connectors() -> dict[str, BankConnector]:
    connectors: list[BankConnector] = [SimpleFinConnector(), PlaidSandboxConnector()]
    return {c.info.id: c for c in connectors}
