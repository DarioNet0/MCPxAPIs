"""Testa o loop do agente (client.py) mockando só a chamada à Anthropic —
a comunicação MCP com o servidor (subprocesso real, via stdio) e a consulta
ao SQLite continuam reais, então isso valida o fluxo completo do agente
decidindo chamar tools e o servidor respondendo de verdade."""

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-used-because-mocked")


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def _usage(input_tokens, output_tokens):
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    db_path = tmp_path / "client_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    from app.config import get_settings

    get_settings.cache_clear()

    from app.db import init_db, get_connection

    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO economic_indicators (country, continent, year, gdp_growth_pct) "
            "VALUES ('Brazil', 'South America', 2023, 2.9)"
        )
    get_settings.cache_clear()
    return str(db_path)


@pytest.mark.asyncio
async def test_agent_loop_calls_tool_then_answers(seeded_db):
    import client as client_module

    call_sequence = [
        SimpleNamespace(
            content=[
                _tool_use_block(
                    "call_1",
                    "query_economic_indicators",
                    {"sql": "SELECT country, gdp_growth_pct FROM economic_indicators WHERE continent = 'South America'"},
                )
            ],
            usage=_usage(120, 40),
        ),
        SimpleNamespace(
            content=[_text_block("O crescimento do PIB da América do Sul em 2023 foi de 2.9% (Brasil).")],
            usage=_usage(90, 35),
        ),
    ]

    mock_anthropic_instance = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **kwargs: call_sequence.pop(0))
    )

    with patch.object(client_module, "Anthropic", return_value=mock_anthropic_instance):
        result = await client_module.answer_question("Qual foi o crescimento do PIB da América do Sul em 2023?")

    assert "2.9" in result.answer
    assert result.metrics["llm_round_trips"] == 2
    assert result.metrics["tool_call_count"] == 1
    assert result.metrics["input_tokens"] == 210
    assert result.metrics["output_tokens"] == 75
    assert result.metrics["rows_returned"] == 1
    assert result.tool_calls[0]["tool"] == "query_economic_indicators"
    assert result.tool_calls[0]["is_error"] is False


@pytest.mark.asyncio
async def test_agent_loop_raises_without_api_key(seeded_db, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    import client as client_module
    from app.config import get_settings

    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await client_module.answer_question("qualquer pergunta")
    get_settings.cache_clear()
