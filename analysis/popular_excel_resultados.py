#!/usr/bin/env python3
"""Preenche resultados_side_by_side.xlsx com os dados reais coletados
(results/logs/side_by_side_log.jsonl), nas abas REST, MCP-Tradicional
e MCP-Contexto. Não mexe nas abas Leia-me/Perguntas/Comparativo/Resumo —
só escreve nas células de dados (fundo amarelo). As fórmulas de
Comparativo/Resumo recalculam sozinhas ao abrir no Excel (ou rode
recalc.py do skill de xlsx antes de entregar).

Uso:
    python popular_excel_resultados.py \
        --log results/logs/side_by_side_log.jsonl \
        --xlsx results/resultados_side_by_side.xlsx
"""
import argparse
import json
from pathlib import Path

from openpyxl import load_workbook

# Mesma ordem/colunas de gerar_planilha_resultados.py, a partir da coluna D.
BASE_METRIC_COLS = [
    "total_latency_ms",
    "llm_round_trips",
    "tool_call_count",       # só MCP
    "input_tokens",
    "output_tokens",
    "rows_returned",
    "request_bytes",
    "response_bytes",
    "llm_bytes_sent",
    "llm_bytes_received",
    "mcp_bytes_sent",        # só MCP
    "mcp_bytes_received",    # só MCP
    "db_payload_bytes",
]
FIRST_COL = 4  # coluna D


def build_question_row_map(ws_perguntas):
    mapping = {}
    for row in range(2, 32):
        q = ws_perguntas.cell(row=row, column=3).value
        if q:
            mapping[q.strip()] = row
    return mapping


def fill_sheet(ws, entries, row_map, extra_metric_cols=None):
    """extra_metric_cols: lista de nomes de métricas extras, na ordem em que
    aparecem depois de BASE_METRIC_COLS (ex.: ["context_bytes_before"])."""
    extra_metric_cols = extra_metric_cols or []
    all_metrics = BASE_METRIC_COLS + extra_metric_cols
    erro_col = FIRST_COL + len(all_metrics)

    filled = 0
    for entry in entries:
        question = entry.get("question", "").strip()
        row = row_map.get(question)
        if row is None:
            print(f"AVISO: pergunta não encontrada na aba Perguntas (pulando): {question[:80]!r}")
            continue

        if not entry.get("_ok", False):
            ws.cell(row=row, column=erro_col, value=str(entry.get("_error", "erro desconhecido"))[:500])
            continue

        metrics = entry.get("metrics", {})
        for i, metric in enumerate(all_metrics):
            col = FIRST_COL + i
            cell = ws.cell(row=row, column=col)
            if cell.value == "n/a":
                continue  # métrica que não se aplica a essa implementação
            if metric in metrics:
                cell.value = metrics[metric]
        filled += 1
    return filled


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", default="results/logs/side_by_side_log.jsonl")
    parser.add_argument("--xlsx", default="results/resultados_side_by_side.xlsx")
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.exists():
        raise SystemExit(f"Log não encontrado: {log_path}.")

    rest_entries, trad_entries, ctx_entries = [], [], []
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            question = entry["question"]
            rest_entries.append({"question": question, **entry["rest"]})
            if "mcp" in entry:
                trad_entries.append({"question": question, **entry["mcp"]})
            if "mcp_contexto" in entry:
                ctx_entries.append({"question": question, **entry["mcp_contexto"]})

    wb = load_workbook(args.xlsx)
    row_map = build_question_row_map(wb["Perguntas"])

    n_rest = fill_sheet(wb["REST"], rest_entries, row_map)
    n_trad = fill_sheet(wb["MCP-Tradicional"], trad_entries, row_map)
    n_ctx = fill_sheet(wb["MCP-Contexto"], ctx_entries, row_map, extra_metric_cols=["context_bytes_before"])

    wb.save(args.xlsx)
    print(f"OK: {n_rest} linhas REST, {n_trad} MCP-Tradicional, {n_ctx} MCP-Contexto preenchidas em {args.xlsx}.")
    print("Lembre de rodar o recalc.py do skill de xlsx (ou abrir e salvar no Excel) para recalcular Comparativo/Resumo.")


if __name__ == "__main__":
    main()
