"""Behaviour against a real (temporary) SQLite file, including the read-only barrier."""

import sqlite3

import pytest

from mcp_data_server.config import Settings
from mcp_data_server.db import Database, QueryRejected
from mcp_data_server.seed import build


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    return build(tmp_path_factory.mktemp("db") / "demo.db", customers=25, seed=1)


def make_db(demo, **overrides) -> Database:
    settings = Settings(
        database_path=str(demo),
        allowed_tables=overrides.pop("allowed_tables", ["customers", "orders", "order_items"]),
        masked_columns=overrides.pop("masked_columns", ["customers.email", "customers.phone"]),
        max_rows=overrides.pop("max_rows", 10),
        audit_log_path=overrides.pop("audit_log_path", ""),
    )
    return Database(settings)


def test_only_allowlisted_tables_are_visible(demo):
    assert make_db(demo).tables() == ["customers", "order_items", "orders"]


def test_columns_report_masking_flags(demo):
    columns = {c["name"]: c for c in make_db(demo).columns("customers")}
    assert columns["email"]["masked"] is True
    assert columns["name"]["masked"] is False
    assert columns["id"]["primary_key"] is True


def test_describe_of_a_hidden_table_is_refused(demo):
    with pytest.raises(QueryRejected):
        make_db(demo).columns("internal_notes")


def test_masked_columns_never_leave_the_server(demo):
    result = make_db(demo).run_query("SELECT id, name, email, phone FROM customers")
    emails = {row[2] for row in result.rows}
    phones = {row[3] for row in result.rows}
    assert emails == {"***"} and phones == {"***"}
    assert all("@" not in str(row[1]) for row in result.rows)


def test_results_are_capped_and_flagged(demo):
    result = make_db(demo, max_rows=5).run_query("SELECT * FROM customers")
    assert result.row_count == 5
    assert result.truncated is True


def test_aggregation_returns_real_numbers(demo):
    result = make_db(demo).run_query(
        "SELECT status, COUNT(*) AS orders FROM orders GROUP BY 1 ORDER BY 2 DESC"
    )
    assert result.columns == ["status", "orders"]
    assert sum(row[1] for row in result.rows) > 0


def test_the_connection_itself_is_read_only(demo):
    """Barrier 1: even a write that bypasses validation fails at SQLite level."""
    database = make_db(demo)
    with database.connect() as connection, pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM customers")


def test_broken_sql_returns_a_clear_error(demo):
    with pytest.raises(QueryRejected, match="SQLite rejected"):
        make_db(demo).run_query("SELECT nope FROM customers")


def test_audit_log_records_every_statement(demo, tmp_path):
    log_path = tmp_path / "audit.log"
    database = make_db(demo, audit_log_path=str(log_path))
    database.run_query("SELECT COUNT(*) FROM orders")
    contents = log_path.read_text(encoding="utf-8")
    assert "SELECT COUNT(*) FROM orders" in contents
    assert "rows in" in contents
