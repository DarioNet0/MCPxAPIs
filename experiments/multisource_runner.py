#!/usr/bin/env python3
"""Experimento secundário: REST vs MCP quando o LLM precisa consumir DUAS
fontes de dados heterogêneas (indicadores econômicos + indicadores de
saúde) em vez de uma só, para testar a hipótese levantada na discussão do
TCC — que a vantagem do MCP (descoberta dinâmica de tools) aparece
justamente quando o número de fontes cresce, porque uma API REST
convencional paga o custo de embutir TODOS os schemas no prompt sempre,
mesmo em perguntas que só precisam de uma fonte.

Fonte 2 (saúde): dados REAIS da World Bank Open Data API
(api.worldbank.org), indicadores SP.DYN.LE00.IN, SH.XPD.CHEX.GD.ZS e
SP.DYN.IMRT.IN, coletados via o navegador embutido (a rede deste sandbox
e a da VM do dispositivo bloqueiam acesso direto à internet por política
de allowlist — só o navegador do usuário conseguiu alcançar a API).
Carregados em data/health/health_indicators.db, um arquivo SQLite
SEPARADO do banco econômico (sem JOIN possível via SQL, simulando duas
fontes de sistemas diferentes de verdade).

Reaproveita call_anthropic/_json_bytes/run_safe_select/UnsafeQueryError/
API_KEY/MODEL de runner.py (mesma base de código, mesmas regras de
segurança de SQL).

Cada pergunta roda em sessão isolada (sem contexto persistente entre
perguntas) — a variável sob teste aqui é o Nº DE FONTES, não persistência
de contexto (que já foi testada separadamente no cenário MCP-Contexto).
"""
import json
import time
from pathlib import Path

import runner
from runner import call_anthropic, _json_bytes, run_safe_select, UnsafeQueryError, ROOT as PROJECT_ROOT

HEALTH_DB = PROJECT_ROOT / "data" / "health" / "health_indicators.db"
HEALTH_SCHEMA_SQL = (PROJECT_ROOT / "data" / "health" / "schema.sql").read_text(encoding="utf-8")
ECON_SCHEMA_SQL = runner.SCHEMA_SQL
ECON_DB = runner.REST_DB  # mesmo banco econômico já usado no restante do projeto

QUESTIONS_FILE = PROJECT_ROOT / "experiments" / "questions" / "perguntas_multisource.txt"
RESULTS_LOG = PROJECT_ROOT / "results" / "logs" / "multisource_log.jsonl"

MAX_AGENT_STEPS = runner.MAX_AGENT_STEPS  # 6, mesmo limite do restante do projeto
_MAX_ROWS_RETURNED = runner._MAX_ROWS_RETURNED  # 200, mesma salvaguarda


# ======================================================= REST multi-fonte =

_GEN_SQL_ECON_TOOL = {
    "name": "generate_sql_economic",
    "description": (
        "Gera uma query SQL SELECT contra o banco de INDICADORES ECONÔMICOS "
        "(tabela economic_indicators). Use quando a pergunta precisar de dados "
        "econômicos (PIB, inflação, desemprego, dívida pública, etc.)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "Query SQL SELECT válida para SQLite."}},
        "required": ["sql"],
    },
}
_GEN_SQL_HEALTH_TOOL = {
    "name": "generate_sql_health",
    "description": (
        "Gera uma query SQL SELECT contra o banco de INDICADORES DE SAÚDE "
        "(tabela health_indicators). Use quando a pergunta precisar de dados "
        "de saúde (expectativa de vida, despesa em saúde, mortalidade infantil)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {"sql": {"type": "string", "description": "Query SQL SELECT válida para SQLite."}},
        "required": ["sql"],
    },
}

_REST_MULTI_SYSTEM = (
    "Você traduz perguntas em linguagem natural em queries SQL SELECT para SQLite. "
    "Há DUAS fontes de dados disponíveis, em bancos SEPARADOS (não é possível fazer "
    "JOIN entre elas via SQL — se a pergunta exigir cruzar as duas, gere uma query "
    "para cada fonte relevante; elas serão combinadas depois).\n\n"
    "FONTE 1 — indicadores econômicos (tabela economic_indicators):\n"
    f"{ECON_SCHEMA_SQL}\n\n"
    "FONTE 2 — indicadores de saúde (tabela health_indicators):\n"
    f"{HEALTH_SCHEMA_SQL}\n\n"
    "Chame generate_sql_economic e/ou generate_sql_health conforme a pergunta exigir "
    "(uma pergunta só de uma área precisa de só uma tool; uma pergunta que cruza as "
    "duas precisa das duas). Gere apenas SELECT, use country_code + year como chave "
    "de cruzamento entre as fontes, e limite resultados a no máximo 200 linhas com "
    "LIMIT quando a pergunta não pedir um valor único."
)


def _run_capped_select(db_path: Path, sql: str) -> list[dict]:
    rows = run_safe_select(db_path, sql)
    if len(rows) > _MAX_ROWS_RETURNED:
        rows = rows[:_MAX_ROWS_RETURNED]
        rows.append({"aviso": f"resultado truncado em {_MAX_ROWS_RETURNED} linhas."})
    return rows


def rest_multi_flow(question: str) -> dict:
    total_start = time.perf_counter()
    request_bytes = _json_bytes({"question": question})

    req1 = {
        "model": runner.MODEL,
        "max_tokens": 1024,
        "system": _REST_MULTI_SYSTEM,
        "tools": [_GEN_SQL_ECON_TOOL, _GEN_SQL_HEALTH_TOOL],
        "tool_choice": {"type": "any"},  # tem que usar pelo menos 1 tool, mas pode usar as 2
        "messages": [{"role": "user", "content": question}],
    }
    resp1, lat1 = call_anthropic(req1)
    bytes_sent_1 = _json_bytes(req1)
    bytes_recv_1 = _json_bytes(resp1)
    in_tok_1 = resp1["usage"]["input_tokens"]
    out_tok_1 = resp1["usage"]["output_tokens"]

    sources_used = []
    all_rows = {}
    sql_exec_start = time.perf_counter()
    for block in resp1["content"]:
        if block.get("type") != "tool_use":
            continue
        sql = block["input"].get("sql", "")
        if block["name"] == "generate_sql_economic":
            sources_used.append("economic")
            all_rows["economic"] = {"sql": sql, "rows": _run_capped_select(ECON_DB, sql)}
        elif block["name"] == "generate_sql_health":
            sources_used.append("health")
            all_rows["health"] = {"sql": sql, "rows": _run_capped_select(HEALTH_DB, sql)}
    sql_execution_latency_ms = (time.perf_counter() - sql_exec_start) * 1000

    if not sources_used:
        raise RuntimeError("O LLM não chamou nenhuma tool de geração de SQL.")

    db_payload_bytes = _json_bytes(all_rows)
    rows_returned = sum(len(v["rows"]) for v in all_rows.values())

    user_prompt = (
        f"Pergunta original do usuário: {question}\n\n"
        f"Dados retornados das fontes consultadas (JSON, uma chave por fonte):\n"
        f"{json.dumps(all_rows, ensure_ascii=False, default=str)}\n\n"
        "Responda de forma clara e contextualizada em português, citando os números "
        "relevantes. Se precisar cruzar as duas fontes, combine os dados usando "
        "country_code + year. Se os dados estiverem vazios, diga isso explicitamente."
    )
    req2 = {
        "model": runner.MODEL,
        "max_tokens": 1024,
        "system": "Você é um assistente analítico especializado em indicadores econômicos e de saúde.",
        "messages": [{"role": "user", "content": user_prompt}],
    }
    resp2, lat2 = call_anthropic(req2)
    bytes_sent_2 = _json_bytes(req2)
    bytes_recv_2 = _json_bytes(resp2)
    answer = "".join(b.get("text", "") for b in resp2["content"] if b.get("type") == "text")
    in_tok_2 = resp2["usage"]["input_tokens"]
    out_tok_2 = resp2["usage"]["output_tokens"]

    total_latency_ms = (time.perf_counter() - total_start) * 1000
    response_body = {"question": question, "sources_used": sources_used, "answer": answer}
    response_bytes = _json_bytes(response_body)

    return {
        "answer": answer,
        "sources_used": sources_used,
        "sql_generated": {k: v["sql"] for k, v in all_rows.items()},
        "metrics": {
            "total_latency_ms": round(total_latency_ms, 2),
            "llm_round_trips": 2,
            "sources_used_count": len(sources_used),
            "sql_generation_latency_ms": round(lat1, 2),
            "sql_execution_latency_ms": round(sql_execution_latency_ms, 2),
            "answer_generation_latency_ms": round(lat2, 2),
            "input_tokens": in_tok_1 + in_tok_2,
            "output_tokens": out_tok_1 + out_tok_2,
            "rows_returned": rows_returned,
            "request_bytes": request_bytes,
            "response_bytes": response_bytes,
            "llm_bytes_sent": bytes_sent_1 + bytes_sent_2,
            "llm_bytes_received": bytes_recv_1 + bytes_recv_2,
            "db_payload_bytes": db_payload_bytes,
        },
    }


# ======================================================== MCP multi-fonte =

_MCP_MULTI_TOOLS = [
    {
        "name": "get_economic_schema",
        "description": "Retorna o schema SQL do banco de indicadores ECONÔMICOS (economic_indicators).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_economic_indicators",
        "description": "Executa um SELECT contra economic_indicators (dados econômicos: PIB, inflação, desemprego, dívida, etc.).",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "Query SQL SELECT válida para SQLite."}},
            "required": ["sql"],
        },
    },
    {
        "name": "get_health_schema",
        "description": "Retorna o schema SQL do banco de indicadores DE SAÚDE (health_indicators).",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_health_indicators",
        "description": "Executa um SELECT contra health_indicators (dados de saúde: expectativa de vida, despesa em saúde, mortalidade infantil).",
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "Query SQL SELECT válida para SQLite."}},
            "required": ["sql"],
        },
    },
]

_MCP_MULTI_SYSTEM = (
    "Você responde perguntas que podem envolver indicadores econômicos, indicadores "
    "de saúde, ou ambos. Use as tools disponíveis: descubra o schema da fonte que for "
    "relevante para a pergunta (só chame get_*_schema das fontes que realmente for "
    "usar) e depois consulte os dados necessários. As duas fontes são bancos "
    "SEPARADOS — não é possível cruzar via SQL, então se a pergunta exigir as duas, "
    "consulte cada uma separadamente e combine o resultado no seu raciocínio. Quando "
    "tiver os dados suficientes, responda em português, citando os números relevantes."
)


def call_mcp_multi_tool(name: str, tool_input: dict):
    if name == "get_economic_schema":
        return ECON_SCHEMA_SQL
    if name == "query_economic_indicators":
        try:
            return _run_capped_select(ECON_DB, tool_input.get("sql", ""))
        except UnsafeQueryError as e:
            return [{"error": str(e)}]
    if name == "get_health_schema":
        return HEALTH_SCHEMA_SQL
    if name == "query_health_indicators":
        try:
            return _run_capped_select(HEALTH_DB, tool_input.get("sql", ""))
        except UnsafeQueryError as e:
            return [{"error": str(e)}]
    raise RuntimeError(f"Tool desconhecida: {name}")


def mcp_multi_flow(question: str) -> dict:
    total_start = time.perf_counter()
    request_bytes = len(question.encode("utf-8"))

    messages = [{"role": "user", "content": question}]
    llm_round_trips = 0
    tool_calls = []
    input_tokens = 0
    output_tokens = 0
    rows_returned = 0
    llm_bytes_sent = 0
    llm_bytes_received = 0
    mcp_bytes_sent = 0
    mcp_bytes_received = 0
    db_payload_bytes = 0
    last_llm_latency = 0.0

    for _ in range(MAX_AGENT_STEPS):
        req = {
            "model": runner.MODEL,
            "max_tokens": 1024,
            "system": _MCP_MULTI_SYSTEM,
            "tools": _MCP_MULTI_TOOLS,
            "messages": messages,
        }
        llm_bytes_sent += _json_bytes(req)
        resp, lat = call_anthropic(req)
        llm_round_trips += 1
        last_llm_latency = lat
        input_tokens += resp["usage"]["input_tokens"]
        output_tokens += resp["usage"]["output_tokens"]
        llm_bytes_received += _json_bytes(resp)

        tool_use_blocks = [b for b in resp["content"] if b.get("type") == "tool_use"]

        if not tool_use_blocks:
            final_text = "".join(b.get("text", "") for b in resp["content"] if b.get("type") == "text")
            sources_used = sorted({
                "economic" if tc["tool"].endswith("economic_schema") or tc["tool"] == "query_economic_indicators" else "health"
                for tc in tool_calls
                if tc["tool"] in ("get_economic_schema", "query_economic_indicators", "get_health_schema", "query_health_indicators")
            })
            total_latency_ms = (time.perf_counter() - total_start) * 1000
            response_bytes = _json_bytes({"question": question, "answer": final_text, "tool_calls": tool_calls})
            return {
                "answer": final_text,
                "tool_calls": tool_calls,
                "sources_used": sources_used,
                "metrics": {
                    "total_latency_ms": round(total_latency_ms, 2),
                    "llm_round_trips": llm_round_trips,
                    "tool_call_count": len(tool_calls),
                    "sources_used_count": len(sources_used),
                    "last_llm_call_latency_ms": round(last_llm_latency, 2),
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "rows_returned": rows_returned,
                    "request_bytes": request_bytes,
                    "response_bytes": response_bytes,
                    "llm_bytes_sent": llm_bytes_sent,
                    "llm_bytes_received": llm_bytes_received,
                    "mcp_bytes_sent": mcp_bytes_sent,
                    "mcp_bytes_received": mcp_bytes_received,
                    "db_payload_bytes": db_payload_bytes,
                },
            }

        messages.append({"role": "assistant", "content": resp["content"]})
        tool_results_content = []
        for block in tool_use_blocks:
            tool_request_bytes = _json_bytes({"name": block["name"], "input": block["input"]})
            call_start = time.perf_counter()
            try:
                payload = call_mcp_multi_tool(block["name"], block["input"])
                is_error = False
            except Exception as e:
                payload = str(e)
                is_error = True
            call_latency_ms = (time.perf_counter() - call_start) * 1000
            result_text = json.dumps(payload, ensure_ascii=False, default=str)

            mcp_bytes_sent += tool_request_bytes
            mcp_bytes_received += len(result_text.encode("utf-8"))

            tool_calls.append(
                {"tool": block["name"], "input": block["input"], "latency_ms": round(call_latency_ms, 2), "is_error": is_error}
            )
            if block["name"] in ("query_economic_indicators", "query_health_indicators") and not is_error and isinstance(payload, list):
                if not (len(payload) == 1 and isinstance(payload[0], dict) and "error" in payload[0]):
                    rows_returned += len(payload)
                    db_payload_bytes += len(result_text.encode("utf-8"))

            tool_results_content.append(
                {"type": "tool_result", "tool_use_id": block["id"], "content": result_text, "is_error": is_error}
            )
        messages.append({"role": "user", "content": tool_results_content})

    raise RuntimeError(f"Agente excedeu o limite de {MAX_AGENT_STEPS} passos sem chegar a uma resposta final.")


# ============================================================= runner ====


def main():
    questions = [l.strip() for l in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    RESULTS_LOG.parent.mkdir(parents=True, exist_ok=True)

    with RESULTS_LOG.open("w", encoding="utf-8") as out:
        for i, q in enumerate(questions, start=1):
            print(f"[{i}/{len(questions)}] REST-multi: {q[:70]!r}", flush=True)
            try:
                rest_result = rest_multi_flow(q)
                rest_result["_ok"] = True
            except Exception as e:
                rest_result = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
            print(f"[{i}/{len(questions)}]   REST-multi ok={rest_result['_ok']} fontes={rest_result.get('sources_used')}", flush=True)

            print(f"[{i}/{len(questions)}] MCP-multi: {q[:70]!r}", flush=True)
            try:
                mcp_result = mcp_multi_flow(q)
                mcp_result["_ok"] = True
            except Exception as e:
                mcp_result = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
            print(f"[{i}/{len(questions)}]   MCP-multi ok={mcp_result['_ok']} fontes={mcp_result.get('sources_used')}", flush=True)

            entry = {"question": q, "rest_multi": rest_result, "mcp_multi": mcp_result}
            out.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            out.flush()

    print("CONCLUIDO", flush=True)


if __name__ == "__main__":
    main()
