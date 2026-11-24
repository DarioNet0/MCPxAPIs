"""Roda a mesma pergunta nos dois cenários do estudo de caso (REST e MCP) e
compara as métricas lado a lado. Este é o script principal da coleta de
dados do TCC (latência, round-trips, tokens, complexidade).

Pré-requisitos:
  - O servidor REST precisa estar rodando (uvicorn app.main:app) em
    outra janela, com o banco já carregado.
  - O mcp-server precisa ter o banco carregado (data/load_data.py já
    rodado) e o .env com ANTHROPIC_API_KEY configurado.

Este script não tem dependências externas (só biblioteca padrão do
Python) de propósito: REST e MCP costumam viver em ambientes/venvs
separados (por causa de conflitos de versão do starlette entre FastAPI e
o SDK do MCP), então o comparador roda por fora dos dois, chamando um via
HTTP e o outro via subprocesso.

Uso:
    python experiments/side_by_side.py "Qual foi a média de crescimento do PIB da América do Sul em 2023?"
    python experiments/side_by_side.py --questions experiments/questions/perguntas.txt
"""

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_SERVER_DIR = REPO_ROOT / "mcp-server"
RESULTS_LOG = REPO_ROOT / "results" / "logs" / "side_by_side_log.jsonl"


def call_rest(question: str, rest_url: str) -> dict:
    body = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        f"{rest_url.rstrip('/')}/query",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            payload["_wall_clock_ms"] = round((time.perf_counter() - start) * 1000, 2)
            payload["_ok"] = True
            return payload
    except urllib.error.URLError as e:
        return {"_ok": False, "_error": str(e), "_wall_clock_ms": round((time.perf_counter() - start) * 1000, 2)}


def call_mcp(question: str, mcp_python: str) -> dict:
    start = time.perf_counter()
    proc = subprocess.run(
        [mcp_python, "client.py", question],
        cwd=str(MCP_SERVER_DIR),
        capture_output=True,
        text=True,
        timeout=120,
    )
    wall_clock_ms = round((time.perf_counter() - start) * 1000, 2)
    if proc.returncode != 0:
        return {"_ok": False, "_error": proc.stderr.strip()[-2000:], "_wall_clock_ms": wall_clock_ms}
    try:
        payload = json.loads(proc.stdout)
        payload["_wall_clock_ms"] = wall_clock_ms
        payload["_ok"] = True
        return payload
    except json.JSONDecodeError:
        return {"_ok": False, "_error": f"saida invalida: {proc.stdout[-2000:]}", "_wall_clock_ms": wall_clock_ms}


def print_comparison(question: str, rest_result: dict, mcp_result: dict) -> None:
    print("=" * 78)
    print(f"PERGUNTA: {question}")
    print("=" * 78)

    print("\n--- REST ---")
    if rest_result["_ok"]:
        print(f"Resposta: {rest_result.get('answer', '')[:300]}")
        m = rest_result.get("metrics", {})
        print(
            f"Latência total: {m.get('total_latency_ms')} ms | round-trips LLM: {m.get('llm_round_trips')} "
            f"| tokens in/out: {m.get('input_tokens')}/{m.get('output_tokens')} | linhas: {m.get('rows_returned')}"
        )
        print(
            f"Bytes — request: {m.get('request_bytes')} | response: {m.get('response_bytes')} "
            f"| LLM sent/recv: {m.get('llm_bytes_sent')}/{m.get('llm_bytes_received')} | db payload: {m.get('db_payload_bytes')}"
        )
    else:
        print(f"ERRO: {rest_result.get('_error')}")

    print("\n--- MCP ---")
    if mcp_result["_ok"]:
        print(f"Resposta: {mcp_result.get('answer', '')[:300]}")
        m = mcp_result.get("metrics", {})
        print(
            f"Latência total: {m.get('total_latency_ms')} ms | round-trips LLM: {m.get('llm_round_trips')} "
            f"| tool calls: {m.get('tool_call_count')} | tokens in/out: {m.get('input_tokens')}/{m.get('output_tokens')} "
            f"| linhas: {m.get('rows_returned')}"
        )
        print(
            f"Bytes — request: {m.get('request_bytes')} | response: {m.get('response_bytes')} "
            f"| LLM sent/recv: {m.get('llm_bytes_sent')}/{m.get('llm_bytes_received')} "
            f"| MCP sent/recv: {m.get('mcp_bytes_sent')}/{m.get('mcp_bytes_received')} | db payload: {m.get('db_payload_bytes')}"
        )
    else:
        print(f"ERRO: {mcp_result.get('_error')}")
    print()


def save_result(question: str, rest_result: dict, mcp_result: dict) -> None:
    RESULTS_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "rest": rest_result,
        "mcp": mcp_result,
    }
    with RESULTS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compara REST x MCP para a mesma pergunta.")
    parser.add_argument("question", nargs="?", help="Pergunta única a testar.")
    parser.add_argument("--questions", help="Arquivo texto com uma pergunta por linha.")
    parser.add_argument("--rest-url", default="http://localhost:8000")
    parser.add_argument("--mcp-python", default=sys.executable, help="Python a usar pro mcp-server (idealmente o do venv dele).")
    args = parser.parse_args()

    if args.questions:
        questions = [line.strip() for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]
    elif args.question:
        questions = [args.question]
    else:
        parser.error("Forneça uma pergunta como argumento ou use --questions arquivo.txt")

    for question in questions:
        rest_result = call_rest(question, args.rest_url)
        mcp_result = call_mcp(question, args.mcp_python)
        print_comparison(question, rest_result, mcp_result)
        save_result(question, rest_result, mcp_result)

    print(f"Resultados salvos em: {RESULTS_LOG}")


if __name__ == "__main__":
    main()
