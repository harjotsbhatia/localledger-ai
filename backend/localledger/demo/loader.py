"""Loads the synthetic dataset through the real import pipeline."""

from __future__ import annotations

from datetime import date
from typing import Any

from localledger.demo.generator import ACCOUNT_FILES, generate
from localledger.ingestion.csv_parser import preview
from localledger.ingestion.importer import ImportResult, import_csv


def get_or_create_account(conn: Any, name: str, type_: str, institution: str,
                          currency: str = "USD") -> int:
    row = conn.execute("SELECT id FROM accounts WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO accounts (name, institution, type, currency) VALUES (?, ?, ?, ?)",
        (name, institution, type_, currency),
    )
    return cursor.lastrowid


def load_demo(conn: Any, end_date: date, seed: int = 20260101) -> list[ImportResult]:
    dataset = generate(end_date, seed)
    results = []
    for account, (filename, type_, institution) in ACCOUNT_FILES.items():
        content = dataset.files[filename]
        mapping = preview(content).suggested_mapping
        if mapping is None:  # pragma: no cover - generator and detector are tested together
            raise RuntimeError("Demo file format was not recognized.")
        account_id = get_or_create_account(conn, account, type_, institution)
        results.append(import_csv(conn, account_id=account_id, filename=filename,
                                  content=content, mapping=mapping))
    return results
