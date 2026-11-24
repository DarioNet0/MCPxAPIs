#!/usr/bin/env python3
"""Roda as 30 perguntas em UMA sessão MCP contínua (contexto mantido entre
perguntas, com PODA de histórico após `runner.KEEP_RECENT_ROUNDS` rodadas —
ver nota em runner.py) e mescla os resultados no side_by_side_log.jsonl
existente, na chave "mcp_contexto" de cada linha (casando pelo texto da
pergunta).

Reroda as 30 perguntas do zero (sessão nova), e não só as que faltaram no
run anterior sem poda: o run anterior falhou justamente porque o contexto
cresceu sem limite, então reaproveitar aquela sessão (ou seu estado parcial)
não faria sentido metodologicamente — o que se quer medir agora é a mesma
política de poda aplicada de ponta a ponta, do início ao fim da bateria.
"""
import json
from pathlib import Path

import runner

ROOT = Path(__file__).resolve().parent.parent  # repo root
LOG_PATH = ROOT / "results" / "logs" / "side_by_side_log.jsonl"
QUESTIONS_FILE = ROOT / "experiments" / "questions" / "perguntas.txt"


def main():
    questions = [l.strip() for l in QUESTIONS_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]

    entries = []
    with LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    by_question = {e["question"]: e for e in entries}

    messages: list = []
    round_starts: list = []
    for i, q in enumerate(questions, start=1):
        print(f"[{i}/30] MCP-contexto: {q[:70]!r}", flush=True)
        try:
            result = runner.mcp_contexto_flow(q, messages, round_starts)
            result["_ok"] = True
        except Exception as e:
            result = {"_ok": False, "_error": f"{type(e).__name__}: {e}"}
        print(f"[{i}/30]   ok={result['_ok']} | contexto acumulado agora: {runner._json_bytes(messages)} bytes", flush=True)

        if q in by_question:
            by_question[q]["mcp_contexto"] = result
        else:
            print(f"AVISO: pergunta não encontrada no log existente: {q!r}")

    with LOG_PATH.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")

    print("CONCLUIDO")


if __name__ == "__main__":
    main()
