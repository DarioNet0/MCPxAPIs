"""Integração com a Anthropic API (Claude Haiku).

Fluxo REST clássico (2 round-trips ao LLM, sem estado de sessão/contexto
persistente — cada chamada é independente, o que é exatamente o ponto de
comparação com o MCP Server no estudo de caso):

  1) NL -> SQL: o LLM recebe a pergunta + schema do banco e devolve uma
     query SELECT (via tool use / function calling).
  2) dados -> resposta: o LLM recebe os dados retornados do SQLite e a
     pergunta original, e devolve uma resposta em linguagem natural.
"""

import json
import time

from anthropic import Anthropic

from app.config import get_settings
from app.db import table_schema_description

_SQL_TOOL = {
    "name": "generate_sql",
    "description": "Gera uma query SQL SELECT para responder à pergunta do usuário sobre indicadores econômicos.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "Query SQL SELECT válida para SQLite, usando apenas a tabela economic_indicators.",
            }
        },
        "required": ["sql"],
    },
}


def _json_bytes(obj) -> int:
    """Tamanho em bytes de um objeto serializado como JSON — usado como
    proxy para o tamanho da mensagem trocada com o LLM, já que o SDK da
    Anthropic não expõe o payload HTTP bruto enviado/recebido."""
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def _response_bytes(response) -> int:
    try:
        return _json_bytes(response.model_dump())
    except Exception:
        return len(str(response).encode("utf-8"))


class LLMResult:
    def __init__(
        self,
        text: str = "",
        sql: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        bytes_sent: int = 0,
        bytes_received: int = 0,
    ):
        self.text = text
        self.sql = sql
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_ms = latency_ms
        self.bytes_sent = bytes_sent
        self.bytes_received = bytes_received


def _client() -> Anthropic:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada. Copie rest-api/.env.example para "
            "rest-api/.env e preencha com sua chave (console.anthropic.com/settings/keys)."
        )
    return Anthropic(api_key=settings.anthropic_api_key)


def generate_sql(question: str) -> LLMResult:
    """Round-trip #1: pergunta em linguagem natural -> SQL."""
    settings = get_settings()
    client = _client()
    schema = table_schema_description()

    system_prompt = (
        "Você traduz perguntas em linguagem natural sobre indicadores macroeconômicos "
        "globais em queries SQL SELECT para SQLite. Use exclusivamente a tabela "
        "economic_indicators, cujo schema é:\n\n"
        f"{schema}\n\n"
        "Regras: gere apenas SELECT (nunca INSERT/UPDATE/DELETE/DROP), "
        "use funções de agregação (AVG, CORR-like via subqueries, etc.) quando fizer sentido, "
        "e limite resultados a no máximo 200 linhas com LIMIT quando a pergunta não pedir um valor único."
    )

    request_payload = {
        "system": system_prompt,
        "tools": [_SQL_TOOL],
        "tool_choice": {"type": "tool", "name": "generate_sql"},
        "messages": [{"role": "user", "content": question}],
    }

    start = time.perf_counter()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        **request_payload,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    sql = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "generate_sql":
            sql = block.input.get("sql")
            break

    if not sql:
        raise RuntimeError("O LLM não retornou uma query SQL válida.")

    return LLMResult(
        sql=sql,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
        bytes_sent=_json_bytes(request_payload),
        bytes_received=_response_bytes(response),
    )


def generate_answer(question: str, rows: list[dict]) -> LLMResult:
    """Round-trip #2: dados retornados do banco -> resposta em linguagem natural."""
    settings = get_settings()
    client = _client()

    user_prompt = (
        f"Pergunta original do usuário: {question}\n\n"
        f"Dados retornados do banco de dados (JSON):\n{json.dumps(rows, ensure_ascii=False, default=str)}\n\n"
        "Responda à pergunta de forma clara e contextualizada em português, "
        "citando os números relevantes. Se os dados estiverem vazios, diga isso explicitamente."
    )

    request_payload = {
        "system": "Você é um assistente analítico especializado em indicadores macroeconômicos globais.",
        "messages": [{"role": "user", "content": user_prompt}],
    }

    start = time.perf_counter()
    response = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        **request_payload,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    text = "".join(block.text for block in response.content if block.type == "text")

    return LLMResult(
        text=text,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        latency_ms=latency_ms,
        bytes_sent=_json_bytes(request_payload),
        bytes_received=_response_bytes(response),
    )
