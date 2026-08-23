"""Testa as funções das tools diretamente (sem passar pelo protocolo MCP)."""

import pytest


@pytest.fixture
def db_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import init_db, get_connection

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO economic_indicators (country, continent, year, gdp_growth_pct) "
            "VALUES ('Brazil', 'South America', 2023, 2.9)"
        )
    yield
    get_settings.cache_clear()


def test_get_database_schema_returns_table_definition(db_env):
    from app.server import get_database_schema

    schema = get_database_schema()
    assert "CREATE TABLE" in schema
    assert "economic_indicators" in schema


def test_query_economic_indicators_happy_path(db_env):
    from app.server import query_economic_indicators

    rows = query_economic_indicators("SELECT country, gdp_growth_pct FROM economic_indicators WHERE year = 2023")
    assert rows == [{"country": "Brazil", "gdp_growth_pct": 2.9}]


def test_query_economic_indicators_rejects_unsafe_sql(db_env):
    from app.server import query_economic_indicators

    result = query_economic_indicators("DROP TABLE economic_indicators")
    assert "error" in result[0]
