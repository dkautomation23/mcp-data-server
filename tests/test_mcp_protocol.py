"""End-to-end over the real MCP protocol: a client session talks to the server.

Uses the SDK's in-memory transport, so this is the same handshake, tool listing
and call flow Claude Desktop performs - just without a subprocess.
"""

import json

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def server(monkeypatch, tmp_path):
    """A server instance bound to a freshly seeded demo database."""
    from mcp_data_server.seed import build

    database_path = build(tmp_path / "demo.db", customers=20, seed=3)

    monkeypatch.setenv("DATABASE_PATH", str(database_path))
    monkeypatch.setenv("ALLOWED_TABLES", "customers,orders")
    monkeypatch.setenv("MASKED_COLUMNS", "customers.email,customers.phone")
    monkeypatch.setenv("AUDIT_LOG_PATH", "")

    import importlib

    from mcp_data_server import config, db, server as server_module

    config.get_settings.cache_clear()
    importlib.reload(db)
    importlib.reload(server_module)
    return server_module.mcp


async def call(session, name: str, **arguments) -> dict:
    result = await session.call_tool(name, arguments)
    return json.loads(result.content[0].text)


async def test_client_sees_every_tool(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        tools = {tool.name for tool in (await session.list_tools()).tools}
    assert tools == {"list_tables", "describe_table", "run_sql", "search", "summarize_column"}


async def test_list_tables_over_the_protocol(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        payload = await call(session, "list_tables")
    names = {entry["table"] for entry in payload["tables"]}
    assert names == {"customers", "orders"}          # internal_notes stays hidden
    assert payload["allowlist_active"] is True


async def test_run_sql_returns_rows_and_blocks_writes(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        ok = await call(session, "run_sql", sql="SELECT COUNT(*) AS n FROM orders")
        blocked = await call(session, "run_sql", sql="DELETE FROM customers")
        hidden = await call(session, "run_sql", sql="SELECT * FROM internal_notes")

    assert ok["rows"][0][0] > 0
    assert "only SELECT" in blocked["error"]
    assert "allowlist" in hidden["error"]


async def test_search_masks_pii(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        payload = await call(session, "search", table="customers", column="name", term="Customer 01")
    assert payload["row_count"] > 0
    assert all(match["email"] == "***" for match in payload["matches"])


async def test_summarize_column_profiles_data(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        payload = await call(session, "summarize_column", table="customers", column="country")
    assert payload["stats"]["distinct_values"] >= 2
    assert payload["top_values"][0]["count"] >= payload["top_values"][-1]["count"]


async def test_unknown_column_returns_a_helpful_error(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        payload = await call(session, "search", table="customers", column="nope", term="x")
    assert "unknown column" in payload["error"]
    assert "country" in payload["available"]


async def test_schema_resource_is_exposed(server):
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        resources = await session.list_resources()
        uris = {str(resource.uri) for resource in resources.resources}
        assert "schema://tables" in uris

        contents = await session.read_resource("schema://tables")
        schema = json.loads(contents.contents[0].text)
    assert set(schema) == {"customers", "orders"}
