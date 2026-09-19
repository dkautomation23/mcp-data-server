# Contributing

Real commands for this repository. `.github/workflows/ci.yml` is the source of
truth if this page and CI ever disagree.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Linux/macOS
pip install -r requirements.txt
python -m mcp_data_server.seed   # builds the demo SQLite file
```

## Before you write code

The four guardrails in `db.py` (read-only connection, statement parsing,
keyword blocklist, allowlist + masking + caps) are independent on purpose —
a change that touches one should not weaken another. A new SQL guardrail
needs a test in `tests/test_guardrails.py` before anything else. Open an
issue first for anything larger, e.g. a new transport or a new tool.

## The one rule that is not negotiable

A new check starts as a failing test. Add it to `tests/test_guardrails.py`
(SQL validation), `tests/test_database.py` (the real seeded database), or
`tests/test_mcp_protocol.py` (the actual MCP handshake, `list_tools`, and
`call_tool` flow) depending on what you are changing. Confirm it fails for
the right reason, then implement.

## Running the tests

```bash
python -m compileall -q .
python -m pytest -q
```

Same two steps CI runs, in that order. 31 tests today.

## Commit messages

Match `git log --oneline` in this repository: mostly a plain imperative
sentence, sometimes `Component: what changed`, or a `type:` prefix for a
larger addition. No ticket prefixes, no emoji. Recent examples:

```
feat: read-only SQL layer with four independent guardrails
test: guardrails, database layer and the MCP protocol itself (31 tests)
Settings: read the environment when constructed, not when imported
Move to the MCP SDK 2.x API
```

## License

Contributions are published under this repository's MIT license.
