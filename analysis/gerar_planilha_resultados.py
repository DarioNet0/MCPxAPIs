#!/usr/bin/env python3
"""Monta o workbook de análise REST x MCP-Tradicional x MCP-Contexto (30
perguntas).

Cria as abas Leia-me, Perguntas, REST, MCP-Tradicional, MCP-Contexto,
Comparativo e Resumo. As três abas de implementação vêm com as 30
perguntas já preenchidas (colunas A-C) e as colunas de métricas vazias,
prontas para receber os dados da bateria de testes (preenchidas
automaticamente por popular_excel_resultados.py). Comparativo e Resumo
usam fórmulas que recalculam sozinhas assim que as três abas forem
preenchidas.

MCP-Tradicional = uma sessão nova por pergunta (descobre o schema toda vez).
MCP-Contexto    = uma única sessão contínua para as 30 perguntas (schema
                  descoberto uma vez só; testa a hipótese de amortização
                  levantada no teste preliminar de 23/08 — e o trade-off
                  de o contexto crescer sem limite a cada pergunta).
"""
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

QUESTIONS_PATH = "experiments/questions/perguntas.txt"
OUT_PATH = "results/resultados_side_by_side.xlsx"

FONT_NAME = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=14)
NOTE_FONT = Font(name=FONT_NAME, italic=True, color="555555")
INPUT_FILL = PatternFill("solid", fgColor="FFF2CC")  # amarelo claro = célula a preencher

with open(QUESTIONS_PATH, encoding="utf-8") as f:
    questions = [line.strip() for line in f if line.strip()]
assert len(questions) == 30, f"esperado 30 perguntas, achei {len(questions)}"


def categoria(i: int) -> str:
    if i <= 10:
        return "Fácil"
    if i <= 20:
        return "Média"
    return "Difícil"


wb = Workbook()

# ---------------------------------------------------------------- Leia-me
ws = wb.active
ws.title = "Leia-me"
ws["A1"] = "TCC — MCP Server x APIs Convencionais: resultados da bateria de 30 perguntas"
ws["A1"].font = TITLE_FONT
ws.column_dimensions["A"].width = 100
notes = [
    "",
    "Como usar esta planilha:",
    "1. Rode a bateria de 30 perguntas em REST e MCP-Tradicional (experiments/side_by_side.py) e a sessão contínua "
    "MCP-Contexto (run_mcp_contexto.py).",
    "2. Rode popular_excel_resultados.py para preencher automaticamente as abas REST / MCP-Tradicional / MCP-Contexto "
    "a partir de results/logs/side_by_side_log.jsonl.",
    "3. As abas Comparativo e Resumo recalculam sozinhas (são fórmulas) assim que as três abas estiverem preenchidas.",
    "",
    "Abas:",
    "  Perguntas       — as 30 perguntas da bateria, com categoria (Fácil / Média / Difícil).",
    "  REST            — uma linha por pergunta, métricas da implementação REST.",
    "  MCP-Tradicional — MCP com uma sessão NOVA por pergunta (descobre o schema do banco toda vez).",
    "  MCP-Contexto    — MCP com UMA sessão contínua para as 30 perguntas (schema descoberto uma vez só; "
    "testa se isso compensa o contexto crescendo a cada pergunta).",
    "  Comparativo     — as três abas lado a lado, calculado por fórmula.",
    "  Resumo          — médias por categoria (Fácil/Média/Difícil) e totais gerais, por fórmula.",
    "",
    "Células com fundo amarelo = dados a preencher (brutos da coleta). O resto é fórmula — não editar à mão.",
]
for idx, line in enumerate(notes, start=2):
    c = ws.cell(row=idx, column=1, value=line)
    c.font = NOTE_FONT if line and not line.endswith(":") else Font(name=FONT_NAME, bold=True)
    c.alignment = Alignment(wrap_text=True)

# ---------------------------------------------------------------- Perguntas
ws = wb.create_sheet("Perguntas")
headers = ["#", "Categoria", "Pergunta"]
for col, h in enumerate(headers, start=1):
    cell = ws.cell(row=1, column=col, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL
for i, q in enumerate(questions, start=1):
    ws.cell(row=i + 1, column=1, value=i)
    ws.cell(row=i + 1, column=2, value=categoria(i))
    ws.cell(row=i + 1, column=3, value=q)
ws.freeze_panes = "A2"
ws.column_dimensions["A"].width = 5
ws.column_dimensions["B"].width = 12
ws.column_dimensions["C"].width = 110

# ---------------------------------------------------------------- REST / MCP*
BASE_METRIC_COLS = [
    # (header, is_mcp_only, number_format)
    ("total_latency_ms", False, "0.00"),
    ("llm_round_trips", False, "0"),
    ("tool_call_count", True, "0"),
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


def build_impl_sheet(name: str, is_mcp: bool, extra_cols=None):
    """extra_cols: lista de (header, number_format) só aplicável quando is_mcp
    (usado para context_bytes_before na aba MCP-Contexto)."""
    extra_cols = extra_cols or []
    ws = wb.create_sheet(name)
    metric_headers = [m[0] for m in BASE_METRIC_COLS] + [c[0] for c in extra_cols] + ["erro"]
    headers = ["#", "Categoria", "Pergunta"] + metric_headers
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
    for i, q in enumerate(questions, start=1):
        row = i + 1
        ws.cell(row=row, column=1, value=i)
        ws.cell(row=row, column=2, value=categoria(i))
        ws.cell(row=row, column=3, value=q)
        col = 4
        for metric, mcp_only, fmt in BASE_METRIC_COLS:
            cell = ws.cell(row=row, column=col)
            applies = is_mcp if mcp_only else True
            if applies:
                cell.fill = INPUT_FILL
                cell.number_format = fmt
            else:
                cell.value = "n/a"
            col += 1
        for _extra_header, fmt in extra_cols:
            cell = ws.cell(row=row, column=col)
            cell.fill = INPUT_FILL
            cell.number_format = fmt
            col += 1
        # coluna "erro" (última) fica sem preenchimento/format especial
    ws.freeze_panes = "D2"
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 60
    for j in range(4, 4 + len(metric_headers)):
        ws.column_dimensions[get_column_letter(j)].width = 16
    return ws


ws_rest = build_impl_sheet("REST", is_mcp=False)
ws_mcp_trad = build_impl_sheet("MCP-Tradicional", is_mcp=True)
ws_mcp_ctx = build_impl_sheet("MCP-Contexto", is_mcp=True, extra_cols=[("context_bytes_before", "#,##0")])

# Colunas fixas (mesmas para as três abas, pela ordem de BASE_METRIC_COLS):
# D=total_latency_ms E=llm_round_trips F=tool_call_count G=input_tokens
# H=output_tokens I=rows_returned J=request_bytes K=response_bytes
# L=llm_bytes_sent M=llm_bytes_received N=mcp_bytes_sent O=mcp_bytes_received
# P=db_payload_bytes  (MCP-Contexto tem ainda Q=context_bytes_before, R=erro;
#  REST e MCP-Tradicional têm Q=erro)

# ---------------------------------------------------------------- Comparativo
ws = wb.create_sheet("Comparativo")
comp_headers = [
    "#", "Categoria", "Pergunta",
    "Latência REST (ms)", "Latência MCP-Trad (ms)", "Latência MCP-Ctx (ms)",
    "Round-trips REST", "Round-trips MCP-Trad", "Round-trips MCP-Ctx",
    "Tool calls MCP-Trad", "Tool calls MCP-Ctx",
    "Tokens totais REST", "Tokens totais MCP-Trad", "Tokens totais MCP-Ctx",
    "Bytes LLM REST (env+rec)", "Bytes LLM MCP-Trad (env+rec)", "Bytes LLM MCP-Ctx (env+rec)",
    "Bytes MCP-servidor Trad (env+rec)", "Bytes MCP-servidor Ctx (env+rec)",
    "Linhas REST", "Linhas MCP-Trad", "Linhas MCP-Ctx",
    "Contexto acumulado antes (Ctx, bytes)",
]
for col, h in enumerate(comp_headers, start=1):
    cell = ws.cell(row=1, column=col, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL


def g(sheet_ref: str, col_letter: str, row: int) -> str:
    """Referência com guarda de célula vazia (ver nota em versões anteriores:
    referência direta a uma célula-fonte vazia devolveria 0 numérico, o que
    contaminaria as médias em AVERAGEIFS)."""
    return f'IF({sheet_ref}!{col_letter}{row}="","",{sheet_ref}!{col_letter}{row})'


REST = "REST"
TRAD = "'MCP-Tradicional'"
CTX = "'MCP-Contexto'"

for i in range(1, 31):
    row = i + 1
    ws.cell(row=row, column=1, value=f"=Perguntas!A{row}")
    ws.cell(row=row, column=2, value=f"=Perguntas!B{row}")
    ws.cell(row=row, column=3, value=f"=Perguntas!C{row}")
    ws.cell(row=row, column=4, value=f"={g(REST, 'D', row)}").number_format = "0.00"
    ws.cell(row=row, column=5, value=f"={g(TRAD, 'D', row)}").number_format = "0.00"
    ws.cell(row=row, column=6, value=f"={g(CTX, 'D', row)}").number_format = "0.00"
    ws.cell(row=row, column=7, value=f"={g(REST, 'E', row)}")
    ws.cell(row=row, column=8, value=f"={g(TRAD, 'E', row)}")
    ws.cell(row=row, column=9, value=f"={g(CTX, 'E', row)}")
    ws.cell(row=row, column=10, value=f"={g(TRAD, 'F', row)}")
    ws.cell(row=row, column=11, value=f"={g(CTX, 'F', row)}")
    ws.cell(row=row, column=12, value=f'=IF({REST}!G{row}="","",{REST}!G{row}+{REST}!H{row})').number_format = "0"
    ws.cell(row=row, column=13, value=f'=IF({TRAD}!G{row}="","",{TRAD}!G{row}+{TRAD}!H{row})').number_format = "0"
    ws.cell(row=row, column=14, value=f'=IF({CTX}!G{row}="","",{CTX}!G{row}+{CTX}!H{row})').number_format = "0"
    ws.cell(row=row, column=15, value=f'=IF({REST}!L{row}="","",{REST}!L{row}+{REST}!M{row})').number_format = "#,##0"
    ws.cell(row=row, column=16, value=f'=IF({TRAD}!L{row}="","",{TRAD}!L{row}+{TRAD}!M{row})').number_format = "#,##0"
    ws.cell(row=row, column=17, value=f'=IF({CTX}!L{row}="","",{CTX}!L{row}+{CTX}!M{row})').number_format = "#,##0"
    ws.cell(row=row, column=18, value=f'=IF({TRAD}!N{row}="","",{TRAD}!N{row}+{TRAD}!O{row})').number_format = "#,##0"
    ws.cell(row=row, column=19, value=f'=IF({CTX}!N{row}="","",{CTX}!N{row}+{CTX}!O{row})').number_format = "#,##0"
    ws.cell(row=row, column=20, value=f"={g(REST, 'I', row)}")
    ws.cell(row=row, column=21, value=f"={g(TRAD, 'I', row)}")
    ws.cell(row=row, column=22, value=f"={g(CTX, 'I', row)}")
    ws.cell(row=row, column=23, value=f"={g(CTX, 'Q', row)}").number_format = "#,##0"

ws.freeze_panes = "D2"
ws.column_dimensions["A"].width = 5
ws.column_dimensions["B"].width = 12
ws.column_dimensions["C"].width = 50
for j in range(4, len(comp_headers) + 1):
    ws.column_dimensions[get_column_letter(j)].width = 18

# ---------------------------------------------------------------- Resumo
ws = wb.create_sheet("Resumo")
ws["A1"] = "Resumo por categoria (médias) — calculado por fórmula a partir da aba Comparativo"
ws["A1"].font = Font(name=FONT_NAME, bold=True, size=12)
resumo_headers = [
    "Categoria",
    "Latência média REST (ms)", "Latência média MCP-Trad (ms)", "Latência média MCP-Ctx (ms)",
    "Round-trips médios REST", "Round-trips médios MCP-Trad", "Round-trips médios MCP-Ctx",
    "Tokens médios REST", "Tokens médios MCP-Trad", "Tokens médios MCP-Ctx",
    "Bytes LLM médios REST", "Bytes LLM médios MCP-Trad", "Bytes LLM médios MCP-Ctx",
    "Linhas médias REST", "Linhas médias MCP-Trad", "Linhas médias MCP-Ctx",
    "Nº de perguntas com dados",
]
for col, h in enumerate(resumo_headers, start=1):
    cell = ws.cell(row=3, column=col, value=h)
    cell.font = HEADER_FONT
    cell.fill = HEADER_FILL

# Colunas da aba Comparativo usadas no Resumo:
# D=Lat REST E=Lat Trad F=Lat Ctx | G=RT REST H=RT Trad I=RT Ctx
# L=Tok REST M=Tok Trad N=Tok Ctx | O=BytesLLM REST P=BytesLLM Trad Q=BytesLLM Ctx
# T=Linhas REST U=Linhas Trad V=Linhas Ctx
COMP_COLS = {
    "lat": ("D", "E", "F"),
    "rt": ("G", "H", "I"),
    "tok": ("L", "M", "N"),
    "bytes": ("O", "P", "Q"),
    "linhas": ("T", "U", "V"),
}

categorias = ["Fácil", "Média", "Difícil", "Total"]
for i, cat in enumerate(categorias):
    row = 4 + i
    ws.cell(row=row, column=1, value=cat)
    crit = f'Comparativo!$B$2:$B$31,"{cat}"'
    col = 2
    for key in ("lat", "rt", "tok", "bytes", "linhas"):
        fmt = "0.00" if key == "lat" else ("0.0" if key == "rt" else ("0" if key == "tok" else ("#,##0" if key == "bytes" else "0.0")))
        for letter in COMP_COLS[key]:
            if cat == "Total":
                formula = f'=IFERROR(AVERAGE(Comparativo!${letter}$2:${letter}$31),"")'
            else:
                formula = f'=IFERROR(AVERAGEIFS(Comparativo!${letter}$2:${letter}$31,{crit}),"")'
            ws.cell(row=row, column=col, value=formula).number_format = fmt
            col += 1
    if cat == "Total":
        ws.cell(row=row, column=col, value="=COUNTA(Comparativo!$B$2:$B$31)")
    else:
        ws.cell(row=row, column=col, value=f'=COUNTIF(Comparativo!$B$2:$B$31,"{cat}")')

ws.column_dimensions["A"].width = 12
for j in range(2, len(resumo_headers) + 1):
    ws.column_dimensions[get_column_letter(j)].width = 20

wb.save(OUT_PATH)
print("Workbook salvo em", OUT_PATH)
