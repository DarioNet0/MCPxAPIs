"""Teste de integração real do protocolo MCP: sobe o server.py como
subprocesso de verdade e conversa com ele via stdio — sem precisar do LLM
nem de rede, só validando que o transporte/protocolo MCP em si funciona
(descoberta de tools, chamada de tools, retorno de resultados)."""

import json
import os
import sys
from pathlib import Path

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    db_path = tmp_path / "stdio_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import init_db, get_connection

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO economic_indicators (country, continent, year, gdp_growth_pct) "
            "VALUES ('Germany', 'Europe', 2023, -0.3)"
        )
    get_settings.cache_clear()
    return str(db_path)


@pytest.mark.asyncio
async def test_full_stdio_round_trip(seeded_db):
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.server"],
        env={**os.environ, "DATABASE_PATH": seeded_db},
        cwd=PROJECT_ROOT,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            tool_names = {t.name for t in tools.tools}
            assert tool_names == {"get_database_schema", "query_economic_indicators"}

            schema_result = await session.call_tool("get_database_schema", {})
            schema_text = "".join(c.text for c in schema_result.content if c.type == "text")
            assert "economic_indicators" in schema_text

            query_result = await session.call_tool(
                "query_economic_indicators",
                {"sql": "SELECT country, gdp_growth_pct FROM economic_indicators WHERE continent = 'Europe'"},
            )
            assert not query_result.is_error
            rows = query_result.structured_content["result"]
            assert rows == [{"country": "Germany", "gdp_growth_pct": -0.3}]

            unsafe_result = await session.call_tool(
                "query_economic_indicators", {"sql": "DROP TABLE economic_indicators"}
            )
            unsafe_rows = unsafe_result.structured_content["result"]
            assert "error" in unsafe_rows[0]
