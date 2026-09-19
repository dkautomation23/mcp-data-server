# Security policy

mcp-data-server gives an MCP client (Claude Desktop, Claude Code, or any
other) read-only, audited access to a SQLite database behind four guardrails
in `db.py`. This file defines what counts as a security issue in that
specific server.

## Reporting

Use GitHub's private vulnerability reporting on this repository: **Security →
Report a vulnerability**. It opens a private thread; nothing becomes public
until there is a fix.

If that is not available to you, email **hello@dkautomation.dev** with
`mcp-data-server` in the subject line.

Include the commit or version you ran, the exact tool call or `run_sql`
statement, and what happened. A proof of concept is welcome; a scanner's raw
output usually is not.

**Do not open a public issue for a vulnerability.**

## Supported versions

No tagged releases yet — the `main` branch is the supported version. Report
against the commit you actually ran.

## What to expect

| | |
|---|---|
| First reply | within 3 working days |
| Assessment | within 7 working days of the first reply |
| Fix or a stated decision not to fix | within 30 days for anything reproducible |

Single-person commitments, not a company SLA.

## Scope

The "catalog" this tool promises to stay inside is `ALLOWED_TABLES` and
`MASKED_COLUMNS`, not a filesystem directory — treat escaping that allowlist
as the equivalent of a path-traversal bug.

In scope:

- Any call to `run_sql`, `search`, `summarize_column`, or `describe_table`
  that reaches a table not listed in `ALLOWED_TABLES`, or returns a column
  listed in `MASKED_COLUMNS` unmasked.
- A statement that executes as more than one `SELECT` / `WITH ... SELECT` —
  a second statement, a write, `ATTACH`, `PRAGMA`, or anything else the
  keyword blocklist and parser in `db.py` are meant to reject.
- A value passed through `search()`'s `term` (or any other tool argument)
  that breaks out of the quoting the query builder relies on.
- The read-only `mode=ro` connection being bypassed so a write reaches the
  actual database file.
- An entry that should have been written to `AUDIT_LOG_PATH` being
  suppressed, or a false one being written.

Out of scope:

- Adapting the server to Postgres/MySQL yourself and finding that the
  SQLite-specific escaping in `search()` does not hold on that engine — the
  README already flags this as something to redo when you change engines;
  it is not a vulnerability in the SQLite version shipped here.
- `ALLOWED_TABLES` left empty (meaning "every table") and the model then
  reading everything — that is the documented default, not a bypass.
- The bundled demo database or seed data.

## Credit

Named in the fix's release notes if you want that; say so if you would rather
not be.

There is no bug bounty.
