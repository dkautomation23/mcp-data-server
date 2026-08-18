"""The guardrails are the product - they get the most tests."""

import pytest

from mcp_data_server.config import Settings
from mcp_data_server.db import Database, QueryRejected, validate_sql

SETTINGS = Settings(
    database_path="demo.db",
    allowed_tables=["customers", "orders"],
    masked_columns=["customers.email"],
    max_rows=50,
    audit_log_path="",
)


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM customers",
        "UPDATE customers SET name = 'x'",
        "INSERT INTO customers VALUES (1)",
        "DROP TABLE customers",
        "ATTACH DATABASE '/etc/passwd' AS leak",
        "PRAGMA table_list",
        "CREATE TABLE t (a INT)",
    ],
)
def test_write_and_admin_statements_are_rejected(sql):
    with pytest.raises(QueryRejected):
        validate_sql(sql, SETTINGS)


def test_second_statement_is_rejected():
    with pytest.raises(QueryRejected, match="one statement"):
        validate_sql("SELECT 1; DROP TABLE customers", SETTINGS)


def test_comment_cannot_smuggle_a_write():
    # The comment is stripped first, so the DELETE becomes visible and is caught.
    with pytest.raises(QueryRejected):
        validate_sql("SELECT 1 -- harmless\nDELETE FROM customers", SETTINGS)


def test_table_outside_the_allowlist_is_rejected():
    with pytest.raises(QueryRejected, match="allowlist"):
        validate_sql("SELECT * FROM internal_notes", SETTINGS)


def test_join_to_a_forbidden_table_is_rejected():
    sql = "SELECT c.name FROM customers c JOIN internal_notes n ON n.customer_id = c.id"
    with pytest.raises(QueryRejected, match="internal_notes"):
        validate_sql(sql, SETTINGS)


def test_empty_allowlist_permits_every_table():
    permissive = Settings(allowed_tables=[], audit_log_path="")
    assert "internal_notes" in validate_sql("SELECT * FROM internal_notes", permissive)


def test_limit_is_added_when_missing_and_kept_when_present():
    # max_rows + 1: the extra row is the sentinel that reveals truncation.
    assert validate_sql("SELECT * FROM customers", SETTINGS).endswith("LIMIT 51")
    assert validate_sql("SELECT * FROM customers LIMIT 5", SETTINGS).endswith("LIMIT 5")


def test_with_clause_is_allowed():
    sql = "WITH recent AS (SELECT * FROM orders) SELECT COUNT(*) FROM recent"
    assert validate_sql(sql, SETTINGS).startswith("WITH")


def test_missing_database_file_is_reported_clearly(tmp_path):
    database = Database(Settings(database_path=str(tmp_path / "nope.db"), audit_log_path=""))
    with pytest.raises(FileNotFoundError, match="database not found"):
        database.tables()
