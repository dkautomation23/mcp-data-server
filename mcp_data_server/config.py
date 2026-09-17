"""Configuration: what the model is allowed to see, and how much of it.

Everything here exists to answer the first question a client asks before
connecting an LLM to their database: "what stops it from reading or breaking
something it shouldn't?"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _csv_env(name: str) -> list[str]:
    """Comma-separated env var -> list of lower-cased, stripped entries."""
    raw = os.getenv(name, "")
    return [item.strip().lower() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True, slots=True)
class Settings:
    # Every default below is a factory, not a plain value. A bare
    # `= os.getenv(...)` is evaluated once, when this module is first imported,
    # so every later `Settings()` would hand back the environment as it looked
    # at import time - and a process that sets its environment after the import
    # (a test, an embedded run, a reload) would silently get the wrong database.

    # SQLite file the server reads. Opened read-only regardless of this path.
    database_path: str = field(default_factory=lambda: os.getenv("DATABASE_PATH", "demo.db"))

    # Tables the model may touch. Empty list = every table in the file.
    # Anything not listed is invisible: it is not described and not queryable.
    allowed_tables: list[str] = field(default_factory=lambda: _csv_env("ALLOWED_TABLES"))

    # Columns replaced with "***" in every result (PII the model never needs).
    # Format: table.column, e.g. customers.email,customers.phone
    masked_columns: list[str] = field(default_factory=lambda: _csv_env("MASKED_COLUMNS"))

    # Hard ceiling on rows returned per call - protects context and the DB.
    max_rows: int = field(default_factory=lambda: int(os.getenv("MAX_ROWS", "200")))

    # Statement timeout. A runaway query is cancelled instead of hanging Claude.
    query_timeout_seconds: float = field(
        default_factory=lambda: float(os.getenv("QUERY_TIMEOUT_SECONDS", "10")))

    # Append every executed statement to this file (audit trail). Empty = off.
    audit_log_path: str = field(default_factory=lambda: os.getenv("AUDIT_LOG_PATH", "audit.log"))

    def is_table_allowed(self, table: str) -> bool:
        return not self.allowed_tables or table.lower() in self.allowed_tables

    def is_masked(self, table: str, column: str) -> bool:
        return f"{table.lower()}.{column.lower()}" in self.masked_columns


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
