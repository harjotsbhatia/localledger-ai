"""Opt-in test against the real SimpleFIN demo Bridge. Sends no personal data.

    LOCALLEDGER_LIVE_NETWORK=1 uv run pytest -m live_network
"""

import os
from datetime import date

import pytest

from localledger.connectors.service import ConnectionService
from localledger.connectors.simplefin import SimpleFinConnector
from localledger.security.secrets import MemorySecretStore

# Published in the SimpleFIN protocol document as a reusable demo token.
DEMO_TOKEN = "aHR0cHM6Ly9icmlkZ2Uuc2ltcGxlZmluLm9yZy9zaW1wbGVmaW4vY2xhaW0vZGVtbw=="


@pytest.mark.live_network
@pytest.mark.skipif(os.environ.get("LOCALLEDGER_LIVE_NETWORK") != "1",
                    reason="set LOCALLEDGER_LIVE_NETWORK=1 to contact the SimpleFIN demo")
def test_simplefin_demo_bridge_end_to_end(db):
    service = ConnectionService(db, MemorySecretStore(), {"simplefin": SimpleFinConnector()})
    connection_id = service.connect("simplefin", {"setup_token": DEMO_TOKEN})
    result = service.sync(connection_id, date.today(), force=True)
    assert result.accounts >= 1
    assert service.sync(connection_id, date.today(), force=True).added == 0  # idempotent
