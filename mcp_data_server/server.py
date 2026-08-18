"""The MCP server: five tools and one resource, over a read-only database.

Run it for Claude Desktop / Claude Code (stdio):

    python -m mcp_data_server

Tools are deliberately small and named after questions a person would ask,
not after SQL features - that is what makes a model use them correctly.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import get_settings
from .db import Database, QueryRejected

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

settings = get_settings()
database = Database(settings)

mcp = FastMCP(
    "business-data",
    instructions=(
        "Read-only access to a business database. Call list_tables first, then "
        "describe_table to learn the columns, then run_sql for anything else. "
        "Every query is capped and audited; writes are impossible."
    ),
)


def _as_json(payload: Any) -> str:
    """MCP tools return text; JSON keeps it parseable for the model."""
    return json.dumps(payload, indent=2, ensure_ascii=False, default=str)


@mcp.tool()
def list_tables() -> str:
    """List the tables the model is allowed to read, with their row counts."""
    tables = [{"table": name, "rows": database.row_count(name)} for name in database.tables()]
    return _as_json({"tables": tables, "allowlist_active": bool(settings.allowed_tables)})


@mcp.tool()
def describe_table(table: str) -> str:
    """Show the columns, types and masked fields of one table, plus 3 sample rows.

    Args:
        table: table name as returned by list_tables.
    """
    try:
        columns = database.columns(table)
        sample = database.run_query(f'SELECT * FROM "{table}" LIMIT 3', table_hint=table)
    except (QueryRejected, FileNotFoundError) as exc:
        return _as_json({"error": str(exc)})
    return _as_json(
        {
            "table": table,
            "rows": database.row_count(table),
            "columns": columns,
            "sample": [dict(zip(sample.columns, row)) for row in sample.rows],
        }
    )


@mcp.tool()
def run_sql(sql: str) -> str:
    """Run one read-only SELECT and return the rows.

    Only a single SELECT (or WITH ... SELECT) statement is accepted, results are
    capped, PII columns are masked, and every call is written to the audit log.

    Args:
        sql: the SELECT statement, e.g. "SELECT country, COUNT(*) FROM customers GROUP BY 1".
    """
    try:
        result = database.run_query(sql)
    except (QueryRejected, FileNotFoundError) as exc:
        return _as_json({"error": str(exc), "hint": "only read-only SELECT statements are allowed"})
    return _as_json(
        {
            "sql": result.sql,
            "columns": result.columns,
            "rows": result.rows,
            "row_count": result.row_count,
            "truncated": result.truncated,
            "elapsed_ms": result.elapsed_ms,
        }
    )


@mcp.tool()
def search(table: str, column: str, term: str, limit: int = 20) -> str:
    """Case-insensitive substring search in one column - no SQL needed.

    Args:
        table: table to search.
        column: column to match against.
        term: text to look for.
        limit: maximum rows to return.
    """
    known = {c["name"] for c in database.columns(table)} if settings.is_table_allowed(table) else set()
    if column not in known:
        return _as_json({"error": f"unknown column '{column}' in '{table}'", "available": sorted(known)})
    safe_limit = max(1, min(limit, settings.max_rows))
    escaped = term.replace("'", "''")
    sql = f"SELECT * FROM \"{table}\" WHERE LOWER(\"{column}\") LIKE LOWER('%{escaped}%') LIMIT {safe_limit}"
    try:
        result = database.run_query(sql, table_hint=table)
    except QueryRejected as exc:
        return _as_json({"error": str(exc)})
    return _as_json(
        {"matches": [dict(zip(result.columns, row)) for row in result.rows], "row_count": result.row_count}
    )


@mcp.tool()
def summarize_column(table: str, column: str) -> str:
    """Profile one column: nulls, distinct values, min/max, top 5 values.

    Useful as a first look at unfamiliar data before writing any SQL.

    Args:
        table: table to profile.
        column: column to profile.
    """
    known = {c["name"] for c in database.columns(table)} if settings.is_table_allowed(table) else set()
    if column not in known:
        return _as_json({"error": f"unknown column '{column}' in '{table}'", "available": sorted(known)})
    stats_sql = (
        f'SELECT COUNT(*) AS total, COUNT("{column}") AS non_null, '
        f'COUNT(DISTINCT "{column}") AS distinct_values, '
        f'MIN("{column}") AS min_value, MAX("{column}") AS max_value FROM "{table}"'
    )
    top_sql = (
        f'SELECT "{column}" AS value, COUNT(*) AS count FROM "{table}" '
        f'GROUP BY 1 ORDER BY 2 DESC LIMIT 5'
    )
    try:
        stats = database.run_query(stats_sql, table_hint=table)
        top = database.run_query(top_sql, table_hint=table)
    except QueryRejected as exc:
        return _as_json({"error": str(exc)})
    return _as_json(
        {
            "table": table,
            "column": column,
            "stats": dict(zip(stats.columns, stats.rows[0])) if stats.rows else {},
            "top_values": [dict(zip(top.columns, row)) for row in top.rows],
        }
    )


@mcp.resource("schema://tables")
def schema_resource() -> str:
    """The full readable schema, so the model can load it without a tool call."""
    return _as_json(
        {table: database.columns(table) for table in database.tables()}
    )


def main() -> None:
    """Entry point for `python -m mcp_data_server` (stdio transport)."""
    logging.getLogger(__name__).info(
        "serving %s (tables: %s, max_rows: %s)",
        settings.database_path,
        ", ".join(settings.allowed_tables) or "all",
        settings.max_rows,
    )
    mcp.run()


if __name__ == "__main__":
    main()
