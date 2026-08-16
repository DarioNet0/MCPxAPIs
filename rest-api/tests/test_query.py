import os
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used-because-mocked")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))

    from app.config import get_settings
    get_settings.cache_clear()

    from app.db import init_db, get_connection
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO economic_indicators (country, continent, year, gdp_growth_pct, inflation_cpi_pct) "
            "VALUES ('Brazil', 'South America', 2023, 2.9, 4.6)"
        )

    from app.main import app
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_query_happy_path(client):
    with patch("app.main.llm.generate_sql") as mock_sql, patch("app.main.llm.generate_answer") as mock_answer:
        from app.llm import LLMResult

        mock_sql.return_value = LLMResult(
            sql="SELECT country, gdp_growth_pct FROM economic_indicators WHERE year = 2023",
            input_tokens=50,
            output_tokens=20,
            latency_ms=120.0,
        )
        mock_answer.return_value = LLMResult(
            text="O crescimento do PIB do Brasil em 2023 foi de 2.9%.",
            input_tokens=80,
            output_tokens=30,
            latency_ms=200.0,
        )

        resp = client.post("/query", json={"question": "Qual foi o crescimento do PIB do Brasil em 2023?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] == [{"country": "Brazil", "gdp_growth_pct": 2.9}]
    assert "2.9" in body["answer"]
    assert body["metrics"]["llm_round_trips"] == 2
    assert body["metrics"]["rows_returned"] == 1
    assert body["metrics"]["input_tokens"] == 130


def test_query_rejects_unsafe_sql(client):
    with patch("app.main.llm.generate_sql") as mock_sql:
        from app.llm import LLMResult

        mock_sql.return_value = LLMResult(sql="DROP TABLE economic_indicators", input_tokens=10, output_tokens=5, latency_ms=50.0)

        resp = client.post("/query", json={"question": "apague tudo"})

    assert resp.status_code == 422


def test_query_missing_api_key(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    from app.config import get_settings
    get_settings.cache_clear()

    resp = client.post("/query", json={"question": "Qual o PIB médio da América do Sul?"})
    assert resp.status_code == 502
    get_settings.cache_clear()
