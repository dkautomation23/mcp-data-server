"""Read-only SQL layer with the guardrails an LLM connection needs.

Four independent barriers, so a single mistake never reaches the data:

1. the connection itself is opened read-only (`mode=ro`) - writes fail at the
   SQLite level even if everything above is bypassed;
2. the statement is parsed: exactly one statement, and it must start with
   SELECT or WITH;
3. a keyword blocklist rejects ATTACH / PRAGMA / DDL and friends;
4. table names in the statement are checked against the allowlist, results are
   truncated to `max_rows`, and masked columns are replaced before returning.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings

log = logging.getLogger(__name__)

# Anything that writes, attaches another file, or touches SQLite internals.
FORBIDDEN_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create", "replace",
    "attach", "detach", "pragma", "vacuum", "reindex", "truncate", "grant",
)
# Identifiers after FROM / JOIN - used for the allowlist check.
TABLE_REF = re.compile(r"\b(?:from|join)\s+[\"'`\[]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)
COMMENTS = re.compile(r"(--[^\n]*)|(/\*.*?\*/)", re.DOTALL)
LIMIT_CLAUSE = re.compile(r"\blimit\s+\d+", re.IGNORECASE)
# Names introduced by a WITH clause: they look like tables in FROM/JOIN but are
# not, so the allowlist must skip them.
CTE_NAME = re.compile(r"(?:\bwith\s+|,\s*)([A-Za-z_][A-Za-z0-9_]*)\s+as\s*\(", re.IGNORECASE)


class QueryRejected(ValueError):
    """The statement never ran: it broke one of the guardrails."""


@dataclass(slots=True)
class QueryResult:
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    elapsed_ms: int
    sql: str


def strip_comments(sql: str) -> str:
    """Remove comments so `-- ` cannot hide a second statement."""
    return COMMENTS.sub(" ", sql)


def validate_sql(sql: str, settings: Settings) -> str:
    """Return the statement to execute, or raise QueryRejected.

    Enforces barriers 2-4; the read-only connection is barrier 1.
    """
    cleaned = strip_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        raise QueryRejected("empty statement")

    if ";" in cleaned:
        raise QueryRejected("only one statement per call is allowed")

    lowered = cleaned.lower()
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise QueryRejected("only SELECT (or WITH ... SELECT) statements are allowed")

    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise QueryRejected(f"'{keyword.upper()}' is not allowed on a read-only connection")

    cte_names = {name.lower() for name in CTE_NAME.findall(cleaned)}
    for table in TABLE_REF.findall(cleaned):
        if table.lower() in cte_names:
            continue  # a CTE alias, not a table
        if not settings.is_table_allowed(table):
            raise QueryRejected(
                f"table '{table}' is not in the allowlist "
                f"(allowed: {', '.join(settings.allowed_tables) or 'all'})"
            )

    # Always bound the result set. The +1 is what makes truncation detectable:
    # if the extra row comes back, there was more data than we return.
    if not LIMIT_CLAUSE.search(lowered):
        cleaned = f"{cleaned} LIMIT {settings.max_rows + 1}"
    return cleaned


class Database:
    """Read-only SQLite access with auditing."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = Path(settings.database_path)

    def connect(self) -> sqlite3.Connection:
        if not self.path.exists():
            raise FileNotFoundError(
                f"database not found: {self.path} (run `python -m mcp_data_server.seed` for a demo one)"
            )
        # mode=ro is the barrier that survives every other bug in this file.
        connection = sqlite3.connect(
            f"file:{self.path.as_posix()}?mode=ro", uri=True,
            timeout=self.settings.query_timeout_seconds,
        )
        connection.row_factory = sqlite3.Row
        # Stop a runaway query instead of blocking the client forever.
        deadline = time.monotonic() + self.settings.query_timeout_seconds
        connection.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
        return connection

    # -- introspection -----------------------------------------------------

    def tables(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        return [row["name"] for row in rows if self.settings.is_table_allowed(row["name"])]

    def columns(self, table: str) -> list[dict[str, Any]]:
        if not self.settings.is_table_allowed(table):
            raise QueryRejected(f"table '{table}' is not in the allowlist")
        if table not in self.tables():
            raise QueryRejected(f"unknown table '{table}'")
        with self.connect() as connection:
            # table_info takes an identifier, so it cannot be a bound parameter;
            # the name is validated against the real table list just above.
            rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [
            {
                "name": row["name"],
                "type": row["type"] or "TEXT",
                "nullable": not row["notnull"],
                "primary_key": bool(row["pk"]),
                "masked": self.settings.is_masked(table, row["name"]),
            }
            for row in rows
        ]

    def row_count(self, table: str) -> int:
        if table not in self.tables():
            raise QueryRejected(f"unknown table '{table}'")
        with self.connect() as connection:
            return connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]

    # -- querying ----------------------------------------------------------

    def run_query(self, sql: str, table_hint: str = "") -> QueryResult:
        """Validate, execute and post-process one SELECT."""
        statement = validate_sql(sql, self.settings)
        started = time.perf_counter()
        try:
            with self.connect() as connection:
                cursor = connection.execute(statement)
                fetched = cursor.fetchmany(self.settings.max_rows + 1)
                columns = [description[0] for description in cursor.description or []]
        except sqlite3.OperationalError as exc:
            self._audit(statement, f"error: {exc}")
            raise QueryRejected(f"SQLite rejected the query: {exc}") from exc

        truncated = len(fetched) > self.settings.max_rows
        rows = [list(row) for row in fetched[: self.settings.max_rows]]
        rows = self._mask(columns, rows, table_hint or self._first_table(statement))

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self._audit(statement, f"{len(rows)} rows in {elapsed_ms}ms")
        shown = LIMIT_CLAUSE.sub(f"LIMIT {self.settings.max_rows}", statement) if truncated else statement
        return QueryResult(columns, rows, len(rows), truncated, elapsed_ms, shown)

    # -- internals ---------------------------------------------------------

    def _first_table(self, sql: str) -> str:
        match = TABLE_REF.search(sql)
        return match.group(1) if match else ""

    def _mask(self, columns: list[str], rows: list[list[Any]], table: str) -> list[list[Any]]:
        """Replace configured PII columns with '***' before anything leaves."""
        if not table:
            return rows
        masked_indexes = [i for i, name in enumerate(columns) if self.settings.is_masked(table, name)]
        if not masked_indexes:
            return rows
        for row in rows:
            for index in masked_indexes:
                row[index] = "***"
        return rows

    def _audit(self, sql: str, outcome: str) -> None:
        if not self.settings.audit_log_path:
            return
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{outcome}\t{' '.join(sql.split())}\n"
        try:
            with open(self.settings.audit_log_path, "a", encoding="utf-8") as handle:
                handle.write(line)
        except OSError as exc:  # auditing must never break a query
            log.warning("audit write failed: %s", exc)
