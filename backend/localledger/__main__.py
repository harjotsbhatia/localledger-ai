"""Sidecar entry point. Started by the desktop shell; binds to loopback only."""

from __future__ import annotations

import os
import sys
import threading
import time

import uvicorn

from localledger.api.app import create_app
from localledger.config import load_config
from localledger.security.keys import get_or_create_db_key
from localledger.security.logging import configure_logging
from localledger.storage.db import Database


def _read_token() -> str:
    # Preferred: first line of stdin, so the secret never appears in the process table.
    token = os.environ.pop("LOCALLEDGER_API_TOKEN", "") or sys.stdin.readline().strip()
    if len(token) < 32:
        sys.exit("LocalLedger backend: no API token supplied; refusing to start.")
    return token


def _exit_with_parent(pid: int) -> None:
    def watch() -> None:
        while True:
            try:
                os.kill(pid, 0)
            except OSError:
                os._exit(0)
            time.sleep(1.5)

    threading.Thread(target=watch, daemon=True).start()


def main() -> None:
    configure_logging()
    config = load_config(_read_token())
    if not config.port:
        sys.exit("LocalLedger backend: LOCALLEDGER_PORT is required.")
    if parent := os.environ.get("LOCALLEDGER_PARENT_PID"):
        _exit_with_parent(int(parent))
    if config.insecure_dev_db:
        print("WARNING: LOCALLEDGER_INSECURE_DEV_DB=1 - database is NOT encrypted.",
              file=sys.stderr)
        db = Database(config.db_path, None, insecure=True)
    else:
        db = Database(config.db_path, get_or_create_db_key())
    db.migrate()
    dev = os.environ.get("LOCALLEDGER_DEV") == "1"
    uvicorn.run(create_app(config, db, log_requests=dev), host="127.0.0.1", port=config.port,
                access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
