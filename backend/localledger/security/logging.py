"""Logging policy: operational metadata only.

Code in this project must never pass transaction descriptions, merchants, amounts, CSV
content, chat text or secrets to a logger. Log counts, ids and durations instead. The
uvicorn access log is disabled because query strings can contain search terms.
"""

from __future__ import annotations

import logging


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").disabled = True
