#!/usr/bin/env python3
"""Roda a bateria de 30 perguntas nos dois cenários (REST e MCP), chamando a
API da Anthropic diretamente via urllib (biblioteca padrão) e replicando
exatamente a lógica de rest-api/app/{llm,db,main}.py e
mcp-server/{app/server.py,client.py} — mesmos prompts, mesmas regras de
segurança de SQL, mesmas métricas (incluindo bytes).

Motivo de existir: nem a VM Linux usada para mexer no PC do Neto nem este
container de nuvem têm acesso ao PyPI (bloqueado pela política de rede),
então não dá para instalar fastapi/anthropic-sdk/mcp-sdk em nenhum dos
dois. Isso aqui reimplementa a lógica com zero dependências externas para
poder rodar a coleta de verdade, com dados reais, chamando a API real.

Grava um .jsonl no MESMO formato que experiments/side_by_side.py grava, para
o popular_excel_resultados.py funcionar sem alterações.
"""
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # repo root
REST_DB = ROOT / "rest-api" / "data" / "economic_indicators.db"
MCP_DB = ROOT / "mcp-server" / "data" / "economic_indicators.db"
SCHEMA_SQL = (ROOT / "rest-api" / "app" / "schema.sql").read_text(encoding="utf-8")
QUESTIONS_FILE = ROOT / "experiments" / "questions" / "perguntas.txt"
RESULTS_DIR = ROOT / "results" / "logs"
RESULTS_LOG = RESULTS_DIR / "side_by_side_log.jsonl"

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

_ALLOWED_STATEMENT = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|PRAGMA|CREATE|REPLACE)\b", re.IGNORECASE)


def parse_env(path) -> dict:
    d = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


_env = parse_env(ROOT / "rest-api" / ".env")
API_KEY = _env["ANTHROPIC_API_KEY"]
MODEL = _env.get("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def _json_bytes(obj) -> int:
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def call_anthropic(payload: dict, max_retries: int = 6) -> tuple[dict, float]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={"x-api-key": API_KEY, "anthropic-version": ANTHROPIC_VERSION, "content-type": "application/json"},
    )
    start = time.perf_counter()
    attempt = 0
    while True:
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                parsed = json.loads(resp.read().decode("utf-8"))
            latency_ms = (time.perf_counter() - start) * 1000
            return parsed, latency_ms
        except urllib.error.HTTPError as e:
            # 429 (rate limit) e 5xx (instabilidade momentânea da API) merecem
            # retry com backoff — sem isso, uma sessão com contexto grande
            # (muitos tokens por chamada) esbarra fácil no limite de
            # tokens-por-minuto da conta e a coleta inteira aborta por um
            # motivo que não tem nada a ver com o protocolo sendo testado.
            if e.code not in (429, 500, 502, 503, 529) or attempt >= max_retries:
                raise
            retry_after = e.headers.get("retry-after") if e.headers else None
            wait_s = float(retry_after) if retry_after else min(60, 2 ** attempt * 2)
            print(f"  [retry] HTTP {e.code}, aguardando {wait_s:.0f}s (tentativa {attempt + 1}/{max_retries})...", flush=True)
            time.sleep(wait_s)
            attempt += 1


class UnsafeQueryError(ValueError):
    pass


def run_safe_select(db_path: Path, sql: str) -> list[dict]:
    if not _ALLOWED_STATEMENT.match(sql):
        raise UnsafeQueryError("Apenas instruções SELECT são permitidas.")
    if _FORBIDDEN_KEYWORDS.search(sql):
        raise UnsafeQueryError("Query contém palavra-chave não permitida.")
    if ";" in sql.strip().rstrip(";"):
        raise UnsafeQueryError("Múltiplas instruções não são permitidas.")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(sql)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]
    finally:
        conn.close()


# ============================================================== REST =====

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

_REST_SQL_SYSTEM = (
    "Você traduz perguntas em linguagem natural sobre indicadores macroeconômicos "
    "globais em queries SQL SELECT para SQLite. Use exclusivamente a tabela "
    "economic_indicators, cujo schema é:\n\n"
    f"{SCHEMA_SQL}\n\n"
    "Regras: gere apenas SELECT (nunca INSERT/UPDATE/DELETE/DROP), "
    "use funções de agregação (AVG, CORR-like via subqueries, etc.) quando fizer sentido, "
    "e limite resultados a no máximo 200 linhas com LIMIT quando a pergunta não pedir um valor único."
)


def rest_flow(question: str) -> dict:
    total_start = time.perf_counter()
    request_bytes = _json_bytes({"question": question, "category": None})

    # Round-trip 1: NL -> SQL
    req1 = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": _REST_SQL_SYSTEM,
        "tools": [_SQL_TOOL],
        "tool_choice": {"type": "tool", "name": "generate_sql"},
        "messages": [{"role": "user", "content": question}],
    }
    resp1, lat1 = call_anthropic(req1)
    bytes_sent_1 = _json_bytes(req1)
    bytes_recv_1 = _json_bytes(resp1)
    sql = None
    for block in resp1["content"]:
        if block.get("type") == "tool_use" and block.get("name") == "generate_sql":
            sql = block["input"].get("sql")
            break
    if not sql:
        raise RuntimeError("O LLM não retornou uma query SQL válida.")
    in_tok_1 = resp1["usage"]["input_tokens"]
    out_tok_1 = resp1["usage"]["output_tokens"]

    sql_exec_start = time.perf_counter()
    rows = run_safe_select(REST_DB, sql)
    sql_execution_latency_ms = (time.perf_counter() - sql_exec_start) * 1000
    db_payload_bytes = _json_bytes(rows)

    # Round-trip 2: dados -> resposta
    user_prompt = (
        f"Pergunta original do usuário: {question}\n\n"
        f"Dados retornados do banco de dados (JSON):\n{json.dumps(rows, ensure_ascii=False, default=str)}\n\n"
        "Responda à pergunta de forma clara e contextualizada em português, "
        "citando os números relevantes. Se os dados estiverem vazios, diga isso explicitamente."
    )
    req2 = {
        "model": MODEL,
        "max_tokens": 1024,
        "system": "Você é um assistente analítico especializado em indicadores macroeconômicos globais.",
        "messages": [{"role": "user", "content": user_prompt}],
    }
    resp2, lat2 = call_anthropic(req2)
    bytes_sent_2 = _json_bytes(req2)
    bytes_recv_2 = _json_bytes(resp2)
    answer = "".join(b.get("text", "") for b in resp2["content"] if b.get("type") == "text")
    in_tok_2 = resp2["usage"]["input_tokens"]
    out_tok_2 = resp2["usage"]["output_tokens"]

    total_latency_ms = (time.perf_counter() - total_start) * 1000
    response_body = {"question": question, "sql_generated": sql, "data": rows, "answer": answer}
    response_bytes = _json_bytes(response_body)

    return {
        "answer": answer,
        "sql_generated": sql,
        "data": rows,
        "metrics": {
            "total_latency_ms": round(total_latency_ms, 2),
            "llm_round_trips": 2,
            "sql_generation_latency_ms": round(lat1, 2),
            "sql_execution_latency_ms": round(sql_execution_latency_ms, 2),
            "answer_generation_latency_ms": round(lat2, 2),
            "input_tokens": in_tok_1 + in_tok_2,
            "output_tokens": out_tok_1 + out_tok_2,
            "rows_returned": len(rows),
            "request_bytes": request_bytes,
            "response_bytes": response_bytes,
            "llm_bytes_sent": bytes_sent_1 + bytes_sent_2,
            "llm_bytes_received": bytes_recv_1 + bytes_recv_2,
            "db_payload_bytes": db_payload_bytes,
        },
    }


# =============================================================== MCP =====

_MCP_TOOLS = [
    {
        "name": "get_database_schema",
        "description": (
            "Retorna o schema SQL da base de indicadores macroeconômicos (tabela "
            "economic_indicators), para a tool descobrir dinamicamente quais colunas "
            "e tipos estão disponíveis antes de montar uma query."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "query_economic_indicators",
        "description": (
            "Executa uma query SQL SELECT (somente leitura) contra a tabela "
            "economic_indicators e retorna as linhas resultantes como uma lista de "
            "objetos. Use LIMIT para evitar retornar muitas linhas de uma vez."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"sql": {"type": "string", "description": "Query SQL SELECT válida para SQLite."}},
            "required": ["sql"],
        },
    },
]

_MCP_SYSTEM = (
    "Você responde perguntas sobre indicadores macroeconômicos globais. "
    "Use as tools disponíveis: primeiro descubra o schema do banco se "
    "precisar, depois consulte os dados necessários (pode chamar a tool "
    "de consulta mais de uma vez se a pergunta exigir cruzar indicadores "
    "diferentes). Quando tiver os dados suficientes, responda em "
    "português, citando os números relevantes."
)

MAX_AGENT_STEPS = 6


_MAX_ROWS_RETURNED = 200  # mesmo teto sugerido ao REST via prompt, aqui aplicado
                          # como salvaguarda do lado do servidor MCP (uma tool
                          # de consulta "de verdade" não devolveria um payload
                          # sem limite só porque o modelo esqueceu de por LIMIT)


def call_mcp_tool(name: str, tool_input: dict):
    """Mesma lógica de mcp-server/app/server.py, chamada em processo (sem
    subprocesso/stdio de verdade — ver nota metodológica no runner.py)."""
    if name == "get_database_schema":
        return SCHEMA_SQL
    if name == "query_economic_indicators":
        try:
            rows = run_safe_select(MCP_DB, tool_input.get("sql", ""))
        except UnsafeQueryError as e:
            return [{"error": str(e)}]
        if len(rows) > _MAX_ROWS_RETURNED:
            rows = rows[:_MAX_ROWS_RETURNED]
            rows.append({
                "aviso": (
                    f"resultado truncado em {_MAX_ROWS_RETURNED} linhas; "
                    "refine a consulta (filtros, agregação) para obter o total."
                )
            })
        return rows
    raise RuntimeError(f"Tool desconhecida: {name}")


def mcp_flow(question: str) -> dict:
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
            "model": MODEL,
            "max_tokens": 1024,
            "system": _MCP_SYSTEM,
            "tools": _MCP_TOOLS,
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
            total_latency_ms = (time.perf_counter() - total_start) * 1000
            response_bytes = _json_bytes({"question": question, "answer": final_text, "tool_calls": tool_calls})
            return {
                "answer": final_text,
                "tool_calls": tool_calls,
                "metrics": {
                    "total_latency_ms": round(total_latency_ms, 2),
                    "llm_round_trips": llm_round_trips,
                    "tool_call_count": len(tool_calls),
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
                payload = call_mcp_tool(block["name"], block["input"])
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
            if block["name"] == "query_economic_indicators" and not is_error and isinstance(payload, list):
                if not (len(payload) == 1 and isinstance(payload[0], dict) and "error" in payload[0]):
                    rows_returned += len(payload)
                    db_payload_bytes += len(result_text.encode("utf-8"))

            tool_results_content.append(
                {"type": "tool_result", "tool_use_id": block["id"], "content": result_text, "is_error": is_error}
            )
        messages.append({"role": "user", "content": tool_results_content})

    raise RuntimeError(f"Agente excedeu o limite de {MAX_AGENT_STEPS} passos sem chegar a uma resposta final.")


# ==================================================== MCP com contexto ===
# Variante que testa a hipótese aberta em 23/08: numa sessão que mantém o
# histórico entre perguntas, a descoberta de schema (get_database_schema)
# só deveria acontecer na primeira pergunta — as seguintes reaproveitam o
# que já está no histórico da conversa. O trade-off é que, como a API de
# mensagens da Anthropic não tem estado no servidor, "manter contexto" na
# prática significa reenviar o histórico inteiro (que só cresce) a cada
# nova pergunta — diferente do REST, que reenvia um schema de tamanho
# FIXO sempre. Esta função opera sobre uma lista `messages` compartilhada
# entre chamadas (passada por referência, mutada in-place) para simular
# uma sessão contínua de principio a fim.
#
# PODA DE HISTÓRICO (adicionada após o primeiro run real mostrar que o
# contexto cru crescia sem limite — de ~2 bytes na pergunta 1 a ~560KB na
# pergunta 20 — até estourar HTTP 400/429 e derrubar as 10 perguntas
# "difícil" da bateria): a cada nova pergunta, a rodada mais antiga que sai
# da janela das últimas `keep_recent` rodadas tem o CONTEÚDO BRUTO dos
# resultados de `query_economic_indicators` (as linhas de dado retornadas
# do banco, que são o que realmente infla o contexto) substituído por um
# resumo curto com a SQL usada e o nº de linhas. A pergunta, a resposta
# final em texto e o resultado de `get_database_schema` (pequeno e
# reaproveitável) são preservados intactos, para a sessão continuar
# coerente e sem precisar redescobrir o schema.

KEEP_RECENT_ROUNDS = 3


def _prune_round(messages: list, start: int, end: int) -> None:
    """Poda in-place a rodada messages[start:end] (uma pergunta já
    respondida): troca o conteúdo de tool_result de query_economic_indicators
    por um resumo curto. Mantém get_database_schema, a pergunta e a resposta
    final intactas."""
    tool_info = {}
    for msg in messages[start:end]:
        if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
            for block in msg["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tool_info[block["id"]] = (block.get("name"), block.get("input", {}))

    for msg in messages[start:end]:
        if msg["role"] != "user" or not isinstance(msg.get("content"), list):
            continue
        for block in msg["content"]:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            name, tool_input = tool_info.get(block.get("tool_use_id"), (None, {}))
            if name != "query_economic_indicators":
                continue  # mantém schema (pequeno) e outros tipos intactos
            content = block.get("content", "")
            if not isinstance(content, str) or len(content) <= 200:
                continue  # já é pequeno (erro, lista vazia, etc.) — não precisa podar
            try:
                n_rows = len(json.loads(content))
            except Exception:
                n_rows = "?"
            sql_preview = str(tool_input.get("sql", ""))[:150]
            block["content"] = (
                f"[PODADO: resultado de {n_rows} linha(s) desta rodada anterior foi "
                "omitido para conter o crescimento do contexto da sessão — a "
                f"pergunta já foi respondida acima. SQL usada: {sql_preview}]"
            )


def _finish_round(messages: list, round_starts: list, round_start_idx: int, keep_recent: int) -> None:
    """Registra o início desta rodada e poda a rodada mais antiga que acabou
    de sair da janela das últimas `keep_recent` rodadas (chamar sempre no
    final da rodada, tanto no caminho de sucesso quanto no de falha)."""
    round_starts.append(round_start_idx)
    if len(round_starts) > keep_recent:
        prune_idx = len(round_starts) - keep_recent - 1
        _prune_round(messages, round_starts[prune_idx], round_starts[prune_idx + 1])


def mcp_contexto_flow(question: str, messages: list, round_starts: list, keep_recent: int = KEEP_RECENT_ROUNDS) -> dict:
    total_start = time.perf_counter()
    request_bytes = len(question.encode("utf-8"))
    context_bytes_before = _json_bytes(messages)
    round_start_idx = len(messages)

    messages.append({"role": "user", "content": question})

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

    try:
        for _ in range(MAX_AGENT_STEPS):
            req = {
                "model": MODEL,
                "max_tokens": 1024,
                "system": _MCP_SYSTEM,
                "tools": _MCP_TOOLS,
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
                messages.append({"role": "assistant", "content": resp["content"]})  # mantém a sessão coerente
                _finish_round(messages, round_starts, round_start_idx, keep_recent)
                total_latency_ms = (time.perf_counter() - total_start) * 1000
                response_bytes = _json_bytes({"question": question, "answer": final_text, "tool_calls": tool_calls})
                return {
                    "answer": final_text,
                    "tool_calls": tool_calls,
                    "metrics": {
                        "total_latency_ms": round(total_latency_ms, 2),
                        "llm_round_trips": llm_round_trips,
                        "tool_call_count": len(tool_calls),
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
                        "context_bytes_before": context_bytes_before,
                    },
                }

            messages.append({"role": "assistant", "content": resp["content"]})
            tool_results_content = []
            for block in tool_use_blocks:
                tool_request_bytes = _json_bytes({"name": block["name"], "input": block["input"]})
                call_start = time.perf_counter()
                try:
                    payload = call_mcp_tool(block["name"], block["input"])
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
                if block["name"] == "query_economic_indicators" and not is_error and isinstance(payload, list):
                    if not (len(payload) == 1 and isinstance(payload[0], dict) and "error" in payload[0]):
                        rows_returned += len(payload)
                        db_payload_bytes += len(result_text.encode("utf-8"))

                tool_results_content.append(
                    {"type": "tool_result", "tool_use_id": block["id"], "content": result_text, "is_error": is_error}
                )
            messages.append({"role": "user", "content": tool_results_content})

        # Estourou o limite de passos: registra uma resposta sintética pra manter
        # a alternância user/assistant válida antes da próxima pergunta da sessão.
        messages.append(
            {"role": "assistant", "content": [{"type": "text", "text": "[não foi possível concluir dentro do limite de passos]"}]}
        )
        _finish_round(messages, round_starts, round_start_idx, keep_recent)
        raise RuntimeError(f"Agente excedeu o limite de {MAX_AGENT_STEPS} passos sem chegar a uma resposta final.")
    except Exception:
        # QUALQUER falha aqui (HTTP 400 por contexto grande demais, limite de
        # passos, etc.) precisa fechar a rodada com uma mensagem assistant
        # válida antes de propagar — senão a próxima pergunta da sessão herda
        # um histórico terminando em "user" (inválido para a API) e TODAS as
        # perguntas seguintes falham em cascata. Foi exatamente isso que
        # aconteceu no primeiro run sem essa proteção: uma falha na pergunta
        # 18 (contexto de ~300KB) derrubou as 12 perguntas seguintes, mesmo
        # com poda de histórico já ativa.
        if not round_starts or round_starts[-1] != round_start_idx:
            if messages and messages[-1]["role"] == "user":
                messages.append(
                    {"role": "assistant", "content": [{"type": "text", "text": "[rodada interrompida por erro]"}]}
                )
            _finish_round(messages, round_starts, round_start_idx, keep_recent)
        raise


# ============================================================= runner ====


def main():
    questions = [l.strip() for l in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    done_questions = set()
    if RESULTS_LOG.exists():
        with RESULTS_LOG.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    done_questions.add(json.loads(line)["question"])

    with RESULTS_LOG.open("a", encoding="utf-8") as out:
        for i, q in enumerate(questions, start=1):
            if q in done_questions:
                print(f"[{i}/30] já coletada, pulando: {q[:60]!r}", flush=True)
                continue

            print(f"[{i}/30] REST: {q[:70]!r}", flush=True)
            try:
                rest_result = rest_flow(q)
                rest_result["_ok"] = True
            except Exception as e:
                rest_result = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
            print(f"[{i}/30]   REST ok={rest_result['_ok']}", flush=True)

            print(f"[{i}/30] MCP: {q[:70]!r}", flush=True)
            try:
                mcp_result = mcp_flow(q)
                mcp_result["_ok"] = True
            except Exception as e:
                mcp_result = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
            print(f"[{i}/30]   MCP ok={mcp_result['_ok']}", flush=True)

            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "question": q,
                "rest": rest_result,
                "mcp": mcp_result,
            }
            out.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            out.flush()

    print("CONCLUIDO", flush=True)


if __name__ == "__main__":
    main()
