import logging

import pytest

from localledger.demo.generator import CARD, CHECKING
from localledger.demo.loader import get_or_create_account, load_demo
from localledger.ingestion.csv_parser import ColumnMapping, CsvError, preview
from localledger.ingestion.importer import import_csv
from tests.conftest import TODAY

MAPPING = ColumnMapping(date="Date", description="Description", amount="Amount", status="Status")


def _account(conn, name="Test"):
    return get_or_create_account(conn, name, "checking", "Bank")


def test_format_detection_for_both_demo_layouts(dataset):
    checking = preview(dataset.files["everyday_checking.csv"]).suggested_mapping
    assert (checking.amount, checking.date_format, checking.status) == (
        "Amount", "YYYY-MM-DD", "Status")
    card = preview(dataset.files["rewards_credit_card.csv"]).suggested_mapping
    assert (card.debit, card.credit, card.amount, card.date_format) == (
        "Debit", "Credit", None, "MM/DD/YYYY")


def test_demo_import_matches_generated_records(db, dataset):
    with db.connect() as conn:
        results = load_demo(conn, TODAY)
        assert sum(r.rows_inserted for r in results) == dataset.golden["transaction_count"]
        assert all(r.rows_invalid == 0 and r.rows_duplicate == 0 for r in results)
        counts = dict(conn.execute(
            "SELECT a.name, COUNT(*) FROM transactions t JOIN accounts a ON a.id = t.account_id"
            " GROUP BY a.name").fetchall())
        assert counts == dataset.golden["transactions_by_account"]
        pending = conn.execute("SELECT COUNT(*) FROM transactions WHERE is_pending = 1")
        assert pending.fetchone()[0] == dataset.golden["pending_count"] == 2


def test_every_demo_row_gets_the_expected_category(db, dataset):
    with db.connect() as conn:
        load_demo(conn, TODAY)
        for account in (CHECKING, CARD):
            expected = sorted((r.day.isoformat(), r.amount_minor, r.category)
                              for r in dataset.records if r.account == account)
            actual = sorted(tuple(row) for row in conn.execute(
                "SELECT t.posted_date, t.amount_minor, t.category FROM transactions t"
                " JOIN accounts a ON a.id = t.account_id WHERE a.name = ?", (account,)))
            assert actual == expected


def test_reimport_is_idempotent(db, dataset):
    with db.connect() as conn:
        load_demo(conn, TODAY)
        before = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        again = load_demo(conn, TODAY)
        assert sum(r.rows_inserted for r in again) == 0
        assert sum(r.rows_duplicate for r in again) == before
        assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == before


def test_identical_same_day_purchases_are_both_kept(db):
    csv = ("Date,Description,Amount,Status\n"
           "2026-10-03,STARBUCKS COFFEE,-5.75,Posted\n"
           "2026-10-03,STARBUCKS COFFEE,-5.75,Posted\n")
    with db.connect() as conn:
        account = _account(conn)
        first = import_csv(conn, account_id=account, filename="a.csv", content=csv,
                           mapping=MAPPING)
        second = import_csv(conn, account_id=account, filename="a.csv", content=csv,
                            mapping=MAPPING)
    assert (first.rows_inserted, second.rows_inserted, second.rows_duplicate) == (2, 0, 2)


def test_overlapping_statements_only_add_new_rows(db):
    january = ("Date,Description,Amount,Status\n2026-01-05,SAFEWAY 1890,-20.00,Posted\n"
               "2026-01-20,SHELL OIL,-40.00,Posted\n")
    overlap = ("Date,Description,Amount,Status\n2026-01-20,SHELL OIL,-40.00,Posted\n"
               "2026-02-02,SAFEWAY 1890,-20.00,Posted\n")
    with db.connect() as conn:
        account = _account(conn)
        import_csv(conn, account_id=account, filename="jan.csv", content=january,
                   mapping=MAPPING)
        result = import_csv(conn, account_id=account, filename="feb.csv", content=overlap,
                            mapping=MAPPING)
    assert (result.rows_inserted, result.rows_duplicate) == (1, 1)


def test_pending_row_settles_instead_of_duplicating(db):
    pending = "Date,Description,Amount,Status\n2026-11-09,LUCKY RAMEN HOUSE,-21.50,Pending\n"
    posted = pending.replace("Pending", "Posted")
    with db.connect() as conn:
        account = _account(conn)
        import_csv(conn, account_id=account, filename="p.csv", content=pending, mapping=MAPPING)
        result = import_csv(conn, account_id=account, filename="p.csv", content=posted,
                            mapping=MAPPING)
        row = conn.execute("SELECT COUNT(*) AS n, SUM(is_pending) AS p FROM transactions")
        assert tuple(row.fetchone()) == (1, 0)
    assert (result.rows_inserted, result.pending_settled) == (0, 1)


def test_invalid_rows_are_reported_not_imported(db):
    csv = ("Date,Description,Amount,Status\n2026-10-01,OK CAFE,-5.00,Posted\n"
           "not-a-date,BAD,-1.00,Posted\n2026-10-02,NO AMOUNT,,Posted\n"
           "2026-10-03,,-3.00,Posted\n")
    with db.connect() as conn:
        result = import_csv(conn, account_id=_account(conn), filename="x.csv", content=csv,
                            mapping=MAPPING)
    assert (result.rows_inserted, result.rows_invalid) == (1, 3)
    assert result.invalid_row_numbers == [3, 4, 5]


def test_positive_is_outflow_convention_and_transfers(db):
    csv = ("Date,Description,Amount\n2026-10-01,NETFLIX.COM,15.49\n"
           "2026-10-02,PAYMENT THANK YOU,-200\n")
    mapping = ColumnMapping(date="Date", description="Description", amount="Amount",
                            amount_convention="positive_is_outflow")
    with db.connect() as conn:
        import_csv(conn, account_id=_account(conn), filename="c.csv", content=csv,
                   mapping=mapping)
        rows = [tuple(r) for r in conn.execute(
            "SELECT amount_minor, category, is_transfer FROM transactions ORDER BY posted_date")]
    assert rows == [(-1549, "Subscriptions", 0), (20000, "Transfer", 1)]


def test_bad_files_and_mappings_are_rejected(db):
    with pytest.raises(CsvError):
        preview("only a header\n")
    with pytest.raises(ValueError, match="amount column"):
        ColumnMapping(date="Date", description="Description")
    with db.connect() as conn, pytest.raises(ValueError, match="not in the file"):
        import_csv(conn, account_id=_account(conn), filename="x.csv",
                   content="Date,Description,Amount\n2026-01-01,X,1\n",
                   mapping=ColumnMapping(date="Date", description="Memo", amount="Amount"))


def test_transaction_content_is_never_logged(db, dataset, caplog):
    caplog.set_level(logging.DEBUG)
    with db.connect() as conn:
        load_demo(conn, TODAY)
    logged = caplog.text.upper()
    for needle in ("STARBUCKS", "PAYROLL", "RENT PAYMENT", "IGNORE PREVIOUS"):
        assert needle not in logged


def test_committed_synthetic_files_match_the_generator(dataset):
    import json
    from pathlib import Path

    folder = Path(__file__).resolve().parents[3] / "data" / "synthetic"
    for name, content in dataset.files.items():
        assert (folder / name).read_text() == content, f"{name} is stale; regenerate it"
    golden = json.loads((folder / "golden_answers.json").read_text())
    assert golden["restaurants_last_month_minor"] == dataset.golden[
        "restaurants_last_month_minor"]
