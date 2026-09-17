# mcp-data-server

[![CI](https://github.com/dkautomation23/mcp-data-server/actions/workflows/ci.yml/badge.svg)](https://github.com/dkautomation23/mcp-data-server/actions/workflows/ci.yml)

Sample project demonstrating production web-scraping / automation patterns.

An **MCP server that gives Claude (or any MCP client) read-only access to a
business database** — with the guardrails that make connecting an LLM to real
company data acceptable: read-only connection, table allowlist, PII masking,
row caps, query timeout and a full audit log.

Ask *"which countries order most, and how much did refunds cost us last
quarter?"* in Claude Desktop and get the answer from the actual database — with
no way for the model to write, drop, attach or read a table it was not granted.

---

## Why this exists

The blocker in most "connect AI to our data" projects is not the wiring, it is
the first question from whoever owns the database: *what stops it from reading
or breaking something it shouldn't?* This server answers that question in code.

## Four independent barriers

| # | Barrier | What it stops |
| --- | --- | --- |
| 1 | Connection opened `mode=ro` | any write, even if every check above it is bypassed |
| 2 | Statement parsing | multiple statements, anything that is not `SELECT` / `WITH` |
| 3 | Keyword blocklist | `ATTACH`, `PRAGMA`, DDL, `VACUUM`, `GRANT` … |
| 4 | Allowlist + masking + caps | tables you did not grant, PII columns, oversized results, runaway queries |

Every executed statement is appended to the audit log with its row count and
duration, so the data owner can see exactly what the model asked for.

```console
2026-08-18T11:22:41  6 rows in 1ms       SELECT country, COUNT(*) FROM customers GROUP BY 1 LIMIT 201
2026-08-18T11:22:44  error: rejected     DELETE FROM customers
```

## Tools exposed

| Tool | Purpose |
| --- | --- |
| `list_tables()` | readable tables + row counts |
| `describe_table(table)` | columns, types, which are masked, 3 sample rows |
| `run_sql(sql)` | one read-only `SELECT`, capped and audited |
| `search(table, column, term, limit)` | substring search without writing SQL |
| `summarize_column(table, column)` | nulls, distinct count, min/max, top 5 values |

Plus a `schema://tables` resource, so a client can load the whole schema
without spending a tool call.

## Quick start

```bash
git clone https://github.com/dkautomation23/mcp-data-server.git
cd mcp-data-server
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m mcp_data_server.seed                    # creates demo.db
cp .env.example .env                              # then point DATABASE_PATH at your file
python -m mcp_data_server                         # serves over stdio
```

Python 3.10+. The demo database has `customers`, `orders`, `order_items` and a
deliberately sensitive `internal_notes` table used below to show the allowlist
blocking access.

### Connect it to Claude Desktop

Add to `claude_desktop_config.json` (full example in
[`examples/claude_desktop_config.json`](examples/claude_desktop_config.json)):

```json
{
  "mcpServers": {
    "business-data": {
      "command": "python",
      "args": ["-m", "mcp_data_server"],
      "cwd": "C:/path/to/mcp-data-server",
      "env": {
        "DATABASE_PATH": "C:/path/to/your.db",
        "ALLOWED_TABLES": "customers,orders,order_items",
        "MASKED_COLUMNS": "customers.email,customers.phone"
      }
    }
  }
}
```

### Connect it to Claude Code

```bash
claude mcp add business-data -- python -m mcp_data_server
```

## What a session looks like

Real output from the running server (see
[`examples/demo_session.md`](examples/demo_session.md) for the full transcript):

```jsonc
// run_sql("SELECT status, COUNT(*) n, ROUND(SUM(total_eur)) revenue FROM orders GROUP BY 1 ORDER BY 3 DESC")
{
  "sql": "SELECT status, COUNT(*) n, ROUND(SUM(total_eur)) revenue FROM orders GROUP BY 1 ORDER BY 3 DESC LIMIT 201",
  "columns": ["status", "n", "revenue"],
  "rows": [["paid", 92, 149914.0], ["pending", 39, 64596.0], ["refunded", 31, 45911.0]],
  "row_count": 3, "truncated": false, "elapsed_ms": 0
}

// run_sql("DELETE FROM customers")
{ "error": "only SELECT (or WITH ... SELECT) statements are allowed" }

// run_sql("SELECT * FROM internal_notes")
{ "error": "table 'internal_notes' is not in the allowlist (allowed: customers, orders, order_items)" }

// run_sql("SELECT id, name, email FROM customers LIMIT 2")
{ "rows": [[1, "Customer 001", "***"], [2, "Customer 002", "***"]] }
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_PATH` | `demo.db` | SQLite file to expose (always opened read-only) |
| `ALLOWED_TABLES` | all | comma-separated allowlist; anything else is invisible |
| `MASKED_COLUMNS` | – | `table.column` list replaced with `***` in every result |
| `MAX_ROWS` | `200` | hard cap per call; results above it are flagged `truncated` |
| `QUERY_TIMEOUT_SECONDS` | `10` | a longer query is cancelled |
| `AUDIT_LOG_PATH` | `audit.log` | append-only log of every statement; empty disables it |

## Tests

```bash
pytest -q
```

```console
...............................                                          [100%]
31 passed in 1.77s
```

Three layers: the SQL guardrails (injection, second statements, comment
smuggling, forbidden tables), the database layer against a real seeded file
(including a write attempt that SQLite itself rejects), and seven tests that
drive the server **over the actual MCP protocol** — the same handshake,
`list_tools` and `call_tool` flow a desktop client performs.

## Adapting it to a client's stack

- **Postgres / MySQL**: replace the connection in `db.py` with a pooled driver
  and a `SET TRANSACTION READ ONLY` session; the validation layer is unchanged.
- **Business-specific tools**: add a function with `@mcp.tool()` in `server.py`
  — a well-named `top_customers(period)` beats making the model write SQL.
- **HTTP transport** instead of stdio: `mcp.run(transport="streamable-http")`,
  then put it behind your own auth.

## License

MIT — see [LICENSE](LICENSE).
