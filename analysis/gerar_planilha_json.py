#!/usr/bin/env python3
"""Adiciona ao workbook existente (resultados_side_by_side.xlsx) as abas do
TERCEIRO experimento: REST-json x MCP-json, a mesma bateria de 15 perguntas
de duas fontes do experimento anterior (Comparativo-Multi), mas SEM SQL —
o LLM só pode chamar uma tool de filtro estruturado (país/continente/ano/
indicador/ordenação/limite), que devolve JSON. Isola o custo de "gerar e
acertar a sintaxe de uma query" do restante da comparação REST x MCP.

Abas novas: Leia-me-Json, Perguntas-Json, REST-Json, MCP-Json,
Comparativo-Json, Resumo-Json. Não mexe nas abas dos experimentos
anteriores.
"""
import json

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

IN_OUT_PATH = "results/resultados_side_by_side.xlsx"
LOG_PATH = "results/logs/json_log.jsonl"

FONT_NAME = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=12)
NOTE_FONT = Font(name=FONT_NAME, italic=True, color="555555")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")

with open(LOG_PATH, encoding="utf-8") as f:
    entries = [json.loads(line) for line in f if line.strip()]
assert len(entries) == 15, f"esperado 15 perguntas, achei {len(entries)}"


def categoria(i: int) -> str:
    if i <= 5:
        return "Econômico"
    if i <= 10:
        return "Saúde"
    return "Cruzado"


wb = load_workbook(IN_OUT_PATH)

for name in ["Perguntas-Json", "REST-Json", "MCP-Json", "Comparativo-Json", "Resumo-Json", "Leia-me-Json"]:
    if name in wb.sheetnames:
        del wb[name]

# ------------------------------------------------------------- Leia-me-Json
ws = wb.create_sheet("Leia-me-Json")
ws["A1"] = "TCC — Experimento 3: REST x MCP consumindo duas fontes SEM SQL (endpoints estruturados)"
ws["A1"].font = Font(name=FONT_NAME, bold=True, size=14)
ws.column_dimensions["A"].width = 105
notes = [
    "",
    "Motivação: nas abas Comparativo/Comparativo-Multi, o LLM gera SQL livre para consultar os dados. Isso é, "
    "na prática, um jeito atípico de expor dados a um LLM — a maioria das APIs REST e servidores MCP reais expõe "
    "ENDPOINTS/TOOLS com parâmetros tipados (país, ano, indicador, ordenação, limite), não uma linguagem de "
    "query livre. Esta terceira variante troca 'gerar SQL' por 'chamar uma tool de filtro estruturado' dos dois "
    "lados (REST e MCP), usando as MESMAS 15 perguntas da aba Comparativo-Multi, pra permitir comparação direta "
    "'com SQL' x 'sem SQL'.",
    "",
    "REST-json: mesmo padrão de 2 round-trips do REST original (1: escolhe filtros via tool; 2: recebe o JSON "
    "filtrado e escreve a resposta) — só que a tool agora tem parâmetros tipados (países, continente, ano, "
    "indicadores, order_by, limit) em vez de um campo de texto SQL.",
    "MCP-json: 2 tools (filter_economic_data, filter_health_data) descobertas dinamicamente — sem tool separada "
    "de schema, porque os indicadores válidos já vêm como enum no próprio schema JSON da tool (autodescritivo).",
    "",
    "RESULTADO: sem SQL, o MCP ficou praticamente empatado com o REST em latência (a diferença de +28% que o "
    "MCP tinha no experimento com SQL caiu pra -2%, ou seja, uma leve vantagem do MCP) — a maior parte do "
    "atraso do MCP no experimento com SQL vinha da descoberta de schema e de tentativa-e-erro de sintaxe/"
    "formatação (ex.: chutar 'JPN' em vez de 'jp'), não da arquitetura de tool-calling em si. Em tokens/bytes "
    "o MCP ainda custa mais (+53% tokens, +41% bytes) — esse resíduo vem de um motivo estrutural real: o loop "
    "de agente do MCP reenvia a definição completa das tools em TODA chamada do loop, enquanto o segundo "
    "round-trip do REST (só escrever a resposta) não carrega tools nenhuma.",
    "",
    "Células com fundo amarelo = dados brutos da coleta. O resto é fórmula.",
]
for idx, line in enumerate(notes, start=2):
    c = ws.cell(row=idx, column=1, value=line)
    c.font = NOTE_FONT if line and not line.endswith(":") else Font(name=FONT_NAME, bold=True)
    c.alignment = Alignment(wrap_text=True)

# -------------------------------------------------------------- Perguntas-Json
ws = wb.create_sheet("Perguntas-Json")
headers = ["#", "Categoria", "Pergunta"]
for col, h in enumerate(headers, start=1):
    cell = ws.cell(row=1, column=col, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
for i, e in enumerate(entries, start=1):
    ws.cell(row=i + 1, column=1, value=i)
    ws.cell(row=i + 1, column=2, value=categoria(i))
    ws.cell(row=i + 1, column=3, value=e["question"])
ws.freeze_panes = "A2"
ws.column_dimensions["A"].width = 5
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 110

# ----------------------------------------------------------- REST-Json / MCP-Json
BASE_METRIC_COLS = [
    ("total_latency_ms", False, "0.00"),
    ("llm_round_trips", False, "0"),
    ("tool_call_count", True, "0"),
    ("sources_used_count", False, "0"),
    ("input_tokens", False, "0"),
    ("output_tokens", False, "0"),
    ("rows_returned", False, "0"),
    ("request_bytes", False, "#,##0"),
    ("response_bytes", False, "#,##0"),
    ("llm_bytes_sent", False, "#,##0"),
    ("llm_bytes_received", False, "#,##0"),
    ("mcp_bytes_sent", True, "#,##0"),
    ("mcp_bytes_received", True, "#,##0"),
    ("db_payload_bytes", False, "#,##0"),
]


def build_impl_sheet(name: str, is_mcp: bool, log_key: str):
    ws = wb.create_sheet(name)
    metric_headers = [m[0] for m in BASE_METRIC_COLS] + ["fontes_usadas", "erro"]
    headers = ["#", "Categoria", "Pergunta"] + metric_headers
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL

    for i, e in enumerate(entries, start=1):
        row = i + 1
        ws.cell(row=row, column=1, value=i)
        ws.cell(row=row, column=2, value=categoria(i))
        ws.cell(row=row, column=3, value=e["question"])
        result = e[log_key]
        metrics = result.get("metrics", {})
        col = 4
        for metric, mcp_only, fmt in BASE_METRIC_COLS:
            cell = ws.cell(row=row, column=col)
            applies = is_mcp if mcp_only else True
            if applies:
                if metric in metrics:
                    cell.value = metrics[metric]
                cell.fill = INPUT_FILL
                cell.number_format = fmt
            else:
                cell.value = "n/a"
            col += 1
        cell = ws.cell(row=row, column=col)
        cell.value = ", ".join(result.get("sources_used", [])) or ""
        cell.fill = INPUT_FILL
        col += 1
        if not result.get("_ok", False):
            ws.cell(row=row, column=col, value=str(result.get("_error", "erro desconhecido"))[:300])

    ws.freeze_panes = "D2"
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 60
    for j in range(4, 4 + len(metric_headers)):
        ws.column_dimensions[get_column_letter(j)].width = 17
    return ws


build_impl_sheet("REST-Json", is_mcp=False, log_key="rest_json")
build_impl_sheet("MCP-Json", is_mcp=True, log_key="mcp_json")

# Colunas fixas (mesma ordem de BASE_METRIC_COLS), a partir de D:
# D=total_latency_ms E=llm_round_trips F=tool_call_count G=sources_used_count
# H=input_tokens I=output_tokens J=rows_returned K=request_bytes L=response_bytes
# M=llm_bytes_sent N=llm_bytes_received O=mcp_bytes_sent P=mcp_bytes_received
# Q=db_payload_bytes R=fontes_usadas S=erro

# ------------------------------------------------------------- Comparativo-Json
ws = wb.create_sheet("Comparativo-Json")
comp_headers = [
    "#", "Categoria", "Pergunta",
    "Latência REST (ms)", "Latência MCP (ms)",
    "Round-trips REST", "Round-trips MCP", "Tool calls MCP",
    "Tokens totais REST", "Tokens totais MCP",
    "Bytes LLM REST (env+rec)", "Bytes LLM MCP (env+rec)",
    "Bytes MCP-servidor (env+rec)",
    "Linhas REST", "Linhas MCP",
    "Fontes usadas REST", "Fontes usadas MCP",
]
for col, h in enumerate(comp_headers, start=1):
    cell = ws.cell(row=1, column=col, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL


def g(sheet_ref: str, col_letter: str, row: int) -> str:
    return f'IF({sheet_ref}!{col_letter}{row}="","",{sheet_ref}!{col_letter}{row})'


REST = "'REST-Json'"
MCP = "'MCP-Json'"

for i in range(1, 16):
    row = i + 1
    ws.cell(row=row, column=1, value=f"='Perguntas-Json'!A{row}")
    ws.cell(row=row, column=2, value=f"='Perguntas-Json'!B{row}")
    ws.cell(row=row, column=3, value=f"='Perguntas-Json'!C{row}")
    ws.cell(row=row, column=4, value=f"={g(REST, 'D', row)}").number_format = "0.00"
    ws.cell(row=row, column=5, value=f"={g(MCP, 'D', row)}").number_format = "0.00"
    ws.cell(row=row, column=6, value=f"={g(REST, 'E', row)}")
    ws.cell(row=row, column=7, value=f"={g(MCP, 'E', row)}")
    ws.cell(row=row, column=8, value=f"={g(MCP, 'F', row)}")
    ws.cell(row=row, column=9, value=f'=IF({REST}!H{row}="","",{REST}!H{row}+{REST}!I{row})').number_format = "0"
    ws.cell(row=row, column=10, value=f'=IF({MCP}!H{row}="","",{MCP}!H{row}+{MCP}!I{row})').number_format = "0"
    ws.cell(row=row, column=11, value=f'=IF({REST}!M{row}="","",{REST}!M{row}+{REST}!N{row})').number_format = "#,##0"
    ws.cell(row=row, column=12, value=f'=IF({MCP}!M{row}="","",{MCP}!M{row}+{MCP}!N{row})').number_format = "#,##0"
    ws.cell(row=row, column=13, value=f'=IF({MCP}!O{row}="","",{MCP}!O{row}+{MCP}!P{row})').number_format = "#,##0"
    ws.cell(row=row, column=14, value=f"={g(REST, 'J', row)}")
    ws.cell(row=row, column=15, value=f"={g(MCP, 'J', row)}")
    ws.cell(row=row, column=16, value=f"={g(REST, 'R', row)}")
    ws.cell(row=row, column=17, value=f"={g(MCP, 'R', row)}")

ws.freeze_panes = "D2"
ws.column_dimensions["A"].width = 5
ws.column_dimensions["B"].width = 14
ws.column_dimensions["C"].width = 50
for j in range(4, len(comp_headers) + 1):
    ws.column_dimensions[get_column_letter(j)].width = 19

# ------------------------------------------------------------------ Resumo-Json
ws = wb.create_sheet("Resumo-Json")
ws["A1"] = "Resumo por categoria (médias) — calculado por fórmula a partir da aba Comparativo-Json"
ws["A1"].font = TITLE_FONT
resumo_headers = [
    "Categoria",
    "Latência média REST (ms)", "Latência média MCP (ms)",
    "Round-trips médios REST", "Round-trips médios MCP",
    "Tokens médios REST", "Tokens médios MCP",
    "Bytes LLM médios REST", "Bytes LLM médios MCP",
    "Linhas médias REST", "Linhas médias MCP",
    "Nº de perguntas com dados",
]
for col, h in enumerate(resumo_headers, start=1):
    cell = ws.cell(row=3, column=col, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL

COMP_COLS = {
    "lat": ("D", "E"),
    "rt": ("F", "G"),
    "tok": ("I", "J"),
    "bytes": ("K", "L"),
    "linhas": ("N", "O"),
}

categorias = ["Econômico", "Saúde", "Cruzado", "Total"]
for i, cat in enumerate(categorias):
    row = 4 + i
    ws.cell(row=row, column=1, value=cat)
    crit = f"'Comparativo-Json'!$B$2:$B$16,\"{cat}\""
    col = 2
    for key in ("lat", "rt", "tok", "bytes", "linhas"):
        fmt = "0.00" if key == "lat" else ("0.0" if key == "rt" else ("0" if key == "tok" else ("#,##0" if key == "bytes" else "0.0")))
        for letter in COMP_COLS[key]:
            if cat == "Total":
                formula = f"=IFERROR(AVERAGE('Comparativo-Json'!${letter}$2:${letter}$16),\"\")"
            else:
                formula = f"=IFERROR(AVERAGEIFS('Comparativo-Json'!${letter}$2:${letter}$16,{crit}),\"\")"
            ws.cell(row=row, column=col, value=formula).number_format = fmt
            col += 1
    if cat == "Total":
        ws.cell(row=row, column=col, value="=COUNTA('Comparativo-Json'!$B$2:$B$16)")
    else:
        ws.cell(row=row, column=col, value=f"=COUNTIF('Comparativo-Json'!$B$2:$B$16,\"{cat}\")")

ws.column_dimensions["A"].width = 14
for j in range(2, len(resumo_headers) + 1):
    ws.column_dimensions[get_column_letter(j)].width = 20

wb.save(IN_OUT_PATH)
print("Abas de json (sem SQL) adicionadas a", IN_OUT_PATH)
print("Sheets:", wb.sheetnames)
