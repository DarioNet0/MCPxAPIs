#!/usr/bin/env python3
"""Terceira variante do experimento multi-fonte: em vez do LLM gerar SQL
(o que é, na prática, um jeito atípico de expor dados a um LLM — a maioria
das APIs REST e servidores MCP reais expõe ENDPOINTS/TOOLS com parâmetros
tipados, não uma linguagem de query livre), o LLM só pode chamar uma tool
de FILTRO ESTRUTURADO (país/continente/ano/indicador/ordenação/limite) que
devolve JSON. O backend monta a consulta internamente (allowlist fixa de
colunas, valores sempre parametrizados) — o LLM nunca vê nem escreve SQL.

Isso isola duas coisas que o experimento com SQL não separava:
  1. custo de "descobrir o schema" (aqui os indicadores válidos já vêm como
     enum no próprio schema da tool — não precisa de uma tool separada de
     schema, nem do lado REST nem do lado MCP);
  2. custo de tentativa-e-erro de sintaxe/formatação SQL (ex.: o LLM
     chutando 'JPN' em vez de 'jp' no experimento anterior) — aqui os
     valores são literais (nome do país por extenso), sem formato para
     errar.

Reaproveita as mesmas 15 perguntas de multisource_runner.py, para permitir
comparação direta "com SQL" x "sem SQL" nas mesmas perguntas.
"""
import json
import time
from pathlib import Path

import runner
from runner import call_anthropic, _json_bytes, ROOT as PROJECT_ROOT
from multisource_runner import ECON_DB, HEALTH_DB, QUESTIONS_FILE

RESULTS_LOG = PROJECT_ROOT / "results" / "logs" / "json_log.jsonl"

ECON_INDICATORS = [
    "gdp_usd", "gdp_growth_pct", "inflation_cpi_pct", "unemployment_rate_pct",
    "real_interest_rate_pct", "government_debt_pct_gdp", "government_revenue_pct_gdp",
    "government_expense_pct_gdp", "current_account_balance_pct_gdp", "gni_usd",
    "tax_revenue_pct_gdp",
]
HEALTH_INDICATORS = ["life_expectancy_years", "health_expenditure_pct_gdp", "infant_mortality_rate"]
CONTINENTS = ["Africa", "Asia", "Europe", "North America", "Oceania", "South America"]

MAX_AGENT_STEPS = runner.MAX_AGENT_STEPS
_MAX_ROWS_RETURNED = runner._MAX_ROWS_RETURNED


def _filter_query(db_path: Path, table: str, has_continent: bool, params: dict) -> list[dict]:
    """Monta e executa uma query SAFE a partir de parâmetros estruturados
    (nunca de texto SQL vindo do LLM). Todo identificador (coluna) vem de uma
    allowlist fixa; todo valor é bound param (?)."""
    allowed = ECON_INDICATORS if table == "economic_indicators" else HEALTH_INDICATORS
    indicators = [i for i in (params.get("indicators") or []) if i in allowed]
    if not indicators:
        indicators = allowed[:1]

    select_cols = ["country", "year"] + indicators
    sql = f"SELECT {', '.join(select_cols)} FROM {table} WHERE 1=1"
    args = []

    countries = params.get("countries")
    if countries:
        placeholders = ",".join("?" for _ in countries)
        sql += f" AND country IN ({placeholders})"
        args.extend(countries)

    if has_continent and params.get("continent") in CONTINENTS:
        sql += " AND continent = ?"
        args.append(params["continent"])

    if params.get("year") is not None:
        sql += " AND year = ?"
        args.append(int(params["year"]))
    else:
        if params.get("year_start") is not None:
            sql += " AND year >= ?"
            args.append(int(params["year_start"]))
        if params.get("year_end") is not None:
            sql += " AND year <= ?"
            args.append(int(params["year_end"]))

    order_by = params.get("order_by")
    if order_by in (indicators + ["country", "year"]):
        direction = "DESC" if params.get("order") == "desc" else "ASC"
        sql += f" ORDER BY {order_by} {direction}"
    else:
        sql += " ORDER BY country, year"

    limit = params.get("limit")
    if isinstance(limit, int) and 0 < limit <= _MAX_ROWS_RETURNED:
        sql += " LIMIT ?"
        args.append(limit)
    else:
        sql += " LIMIT ?"
        args.append(_MAX_ROWS_RETURNED)

    import sqlite3
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute(sql, args)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def filter_economic(params: dict) -> list[dict]:
    return _filter_query(ECON_DB, "economic_indicators", True, params)


def filter_health(params: dict) -> list[dict]:
    return _filter_query(HEALTH_DB, "health_indicators", False, params)


def _filter_tool(name: str, table_desc: str, indicators: list, has_continent: bool) -> dict:
    props = {
        "countries": {"type": "array", "items": {"type": "string"}, "description": "Nomes exatos de países (ex: 'Brazil'). Omitir para não filtrar por país."},
        "year": {"type": "integer", "description": "Ano exato. Omitir se usar year_start/year_end."},
        "year_start": {"type": "integer"},
        "year_end": {"type": "integer"},
        "indicators": {"type": "array", "items": {"type": "string", "enum": indicators}, "description": "Quais métricas retornar (obrigatório)."},
        "order_by": {"type": "string", "enum": indicators + ["country", "year"]},
        "order": {"type": "string", "enum": ["asc", "desc"]},
        "limit": {"type": "integer", "description": f"Máximo de linhas (até {_MAX_ROWS_RETURNED})."},
    }
    if has_continent:
        props["continent"] = {"type": "string", "enum": CONTINENTS}
    return {
        "name": name,
        "description": f"Consulta filtrada e ordenada contra {table_desc}. Não usa SQL — só parâmetros estruturados.",
        "input_schema": {"type": "object", "properties": props, "required": ["indicators"]},
    }


ECON_TOOL_REST = _filter_tool("filter_economic_data", "indicadores ECONÔMICOS (PIB, inflação, desemprego, dívida, etc.)", ECON_INDICATORS, True)
HEALTH_TOOL_REST = _filter_tool("filter_health_data", "indicadores DE SAÚDE (expectativa de vida, despesa em saúde, mortalidade infantil)", HEALTH_INDICATORS, False)

_REST_JSON_SYSTEM = (
    "Você responde perguntas sobre indicadores econômicos e/ou de saúde usando tools de filtro "
    "estruturado (sem SQL). Há duas fontes SEPARADAS (não dá pra cruzar via query — se a pergunta "
    "exigir as duas, chame as duas tools e combine o resultado no seu raciocínio). Escolha os "
    "indicadores, filtros (país/continente/ano) e ordenação relevantes para a pergunta. Chame "
    "filter_economic_data e/ou filter_health_data conforme a pergunta exigir."
)


def rest_json_flow(question: str) -> dict:
    total_start = time.perf_counter()
    request_bytes = _json_bytes({"question": question})

    req1 = {
        "model": runner.MODEL,
        "max_tokens": 1024,
        "system": _REST_JSON_SYSTEM,
        "tools": [ECON_TOOL_REST, HEALTH_TOOL_REST],
        "tool_choice": {"type": "any"},
        "messages": [{"role": "user", "content": question}],
    }
    resp1, lat1 = call_anthropic(req1)
    bytes_sent_1 = _json_bytes(req1)
    bytes_recv_1 = _json_bytes(resp1)
    in_tok_1 = resp1["usage"]["input_tokens"]
    out_tok_1 = resp1["usage"]["output_tokens"]

    sources_used = []
    all_rows = {}
    exec_start = time.perf_counter()
    for block in resp1["content"]:
        if block.get("type") != "tool_use":
            continue
        params = block["input"]
        if block["name"] == "filter_economic_data":
            sources_used.append("economic")
            all_rows["economic"] = {"params": params, "rows": filter_economic(params)}
        elif block["name"] == "filter_health_data":
            sources_used.append("health")
            all_rows["health"] = {"params": params, "rows": filter_health(params)}
    exec_latency_ms = (time.perf_counter() - exec_start) * 1000

    if not sources_used:
        raise RuntimeError("O LLM não chamou nenhuma tool de filtro.")

    db_payload_bytes = _json_bytes(all_rows)
    rows_returned = sum(len(v["rows"]) for v in all_rows.values())

    user_prompt = (
        f"Pergunta original do usuário: {question}\n\n"
        f"Dados retornados das fontes consultadas (JSON, uma chave por fonte):\n"
        f"{json.dumps(all_rows, ensure_ascii=False, default=str)}\n\n"
        "Responda de forma clara e contextualizada em português, citando os números relevantes. "
        "Se precisar cruzar as duas fontes, combine usando país + ano. Se os dados estiverem vazios, diga isso."
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
    response_bytes = _json_bytes({"question": question, "sources_used": sources_used, "answer": answer})

    return {
        "answer": answer,
        "sources_used": sources_used,
        "params_used": {k: v["params"] for k, v in all_rows.items()},
        "metrics": {
            "total_latency_ms": round(total_latency_ms, 2),
            "llm_round_trips": 2,
            "sources_used_count": len(sources_used),
            "sql_generation_latency_ms": round(lat1, 2),
            "sql_execution_latency_ms": round(exec_latency_ms, 2),
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


# =========================================================== MCP sem SQL ==

ECON_TOOL_MCP = _filter_tool("filter_economic_data", "indicadores ECONÔMICOS (PIB, inflação, desemprego, dívida, etc.)", ECON_INDICATORS, True)
HEALTH_TOOL_MCP = _filter_tool("filter_health_data", "indicadores DE SAÚDE (expectativa de vida, despesa em saúde, mortalidade infantil)", HEALTH_INDICATORS, False)
_MCP_JSON_TOOLS = [ECON_TOOL_MCP, HEALTH_TOOL_MCP]

_MCP_JSON_SYSTEM = (
    "Você responde perguntas que podem envolver indicadores econômicos, indicadores de saúde, ou "
    "ambos, usando tools de filtro estruturado (sem SQL). As duas fontes são SEPARADAS — se a "
    "pergunta exigir as duas, chame as duas tools e combine o resultado no seu raciocínio. Quando "
    "tiver os dados suficientes, responda em português, citando os números relevantes."
)


def call_mcp_json_tool(name: str, params: dict):
    if name == "filter_economic_data":
        return filter_economic(params)
    if name == "filter_health_data":
        return filter_health(params)
    raise RuntimeError(f"Tool desconhecida: {name}")


def mcp_json_flow(question: str) -> dict:
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
            "system": _MCP_JSON_SYSTEM,
            "tools": _MCP_JSON_TOOLS,
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
                "economic" if tc["tool"] == "filter_economic_data" else "health" for tc in tool_calls
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
                payload = call_mcp_json_tool(block["name"], block["input"])
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
            if not is_error and isinstance(payload, list):
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
            print(f"[{i}/{len(questions)}] REST-json: {q[:70]!r}", flush=True)
            try:
                r = rest_json_flow(q); r["_ok"] = True
            except Exception as e:
                r = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
            print(f"  REST-json ok={r['_ok']} fontes={r.get('sources_used')} rows={r.get('metrics',{}).get('rows_returned')}", flush=True)

            print(f"[{i}/{len(questions)}] MCP-json: {q[:70]!r}", flush=True)
            try:
                m = mcp_json_flow(q); m["_ok"] = True
            except Exception as e:
                m = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
            print(f"  MCP-json ok={m['_ok']} fontes={m.get('sources_used')}", flush=True)

            entry = {"question": q, "rest_json": r, "mcp_json": m}
            out.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            out.flush()

    print("CONCLUIDO", flush=True)


if __name__ == "__main__":
    main()
