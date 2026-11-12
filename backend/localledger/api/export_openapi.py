"""Writes the OpenAPI schema used to generate the frontend's TypeScript types."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from localledger.api.app import create_app
from localledger.config import Config
from localledger.storage.db import Database


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        config = Config(data_dir=Path(tmp), api_token="x" * 32)
        app = create_app(config, Database(config.db_path, b"\0" * 32))
        app.openapi_url = "/openapi.json"
        schema = json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(schema)
    else:
        sys.stdout.write(schema)


if __name__ == "__main__":
    main()
