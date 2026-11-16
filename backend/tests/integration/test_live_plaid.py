"""Opt-in test against the real Plaid Sandbox, using your own Sandbox keys.

    PLAID_CLIENT_ID=... PLAID_SANDBOX_SECRET=... uv run pytest -m live_network
"""

import os

import pytest

from localledger.connectors.plaid import PlaidSandboxConnector
from localledger.connectors.service import ConnectionService
from localledger.security.secrets import MemorySecretStore
from tests.conftest import TODAY


@pytest.mark.live_network
@pytest.mark.skipif(not (os.environ.get("PLAID_CLIENT_ID")
                         and os.environ.get("PLAID_SANDBOX_SECRET")),
                    reason="set PLAID_CLIENT_ID and PLAID_SANDBOX_SECRET to contact Plaid Sandbox")
def test_plaid_sandbox_end_to_end(db):
    service = ConnectionService(db, MemorySecretStore(),
                                {"plaid_sandbox": PlaidSandboxConnector()})
    connection_id = service.connect("plaid_sandbox", {
        "client_id": os.environ["PLAID_CLIENT_ID"],
        "secret": os.environ["PLAID_SANDBOX_SECRET"], "institution_id": "ins_109508"})
    result = service.sync(connection_id, TODAY, force=True)
    assert result.accounts >= 1 and result.added > 0
    assert service.sync(connection_id, TODAY, force=True).added == 0  # idempotent
    assert service.disconnect(connection_id, delete_data=True)
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
