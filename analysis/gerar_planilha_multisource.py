#!/usr/bin/env python3
"""Adiciona ao workbook existente (resultados_side_by_side.xlsx) as abas do
experimento secundário: REST-multi x MCP-multi, quando o LLM precisa
consumir DUAS fontes de dados heterogêneas (econômica + saúde) em vez de
uma só. Mesmas convenções visuais das abas originais (fonte Arial, cabeçalho
azul, células de dado bruto em amarelo, fórmulas em Comparativo/Resumo).

Abas novas: Perguntas-Multi, REST-Multi, MCP-Multi, Comparativo-Multi,
Resumo-Multi. Não mexe nas abas do experimento original.
"""
import json

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

IN_OUT_PATH = "results/resultados_side_by_side.xlsx"
LOG_PATH = "results/logs/multisource_log.jsonl"

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

# Remove abas de uma execução anterior deste script, se houver (reprocessamento idempotente)
for name in ["Perguntas-Multi", "REST-Multi", "MCP-Multi", "Comparativo-Multi", "Resumo-Multi", "Leia-me-Multi"]:
    if name in wb.sheetnames:
        del wb[name]

# ------------------------------------------------------------ Leia-me-Multi
ws = wb.create_sheet("Leia-me-Multi")
ws["A1"] = "TCC — Experimento secundário: REST x MCP consumindo DUAS fontes de dados"
ws["A1"].font = Font(name=FONT_NAME, bold=True, size=14)
ws.column_dimensions["A"].width = 105
notes = [
    "",
    "Motivação: no experimento principal (abas REST/MCP-Tradicional/MCP-Contexto), a API REST venceu em "
    "latência e custo em todas as categorias, usando uma única fonte de dados (economic_indicators) com schema "
    "fixo embutido no prompt. Isso levantou a pergunta: será que a vantagem do MCP (descoberta dinâmica de "
    "schema/tools) aparece quando o número de fontes de dados cresce — já que uma API REST convencional "
    "precisaria embutir TODOS os schemas no prompt sempre, mesmo em perguntas que só precisam de uma fonte?",
    "",
    "Fonte 2 adicionada: indicadores de saúde (expectativa de vida ao nascer, despesa em saúde % do PIB, "
    "mortalidade infantil), dados REAIS coletados da World Bank Open Data API (api.worldbank.org), "
    "217 países x 2010-2025. Banco SQLite SEPARADO do econômico (data/health/health_indicators.db) — sem "
    "possibilidade de JOIN via SQL entre as duas fontes, simulando dois sistemas de fato distintos.",
    "",
    "REST-multi: system prompt embute os DOIS schemas sempre; duas tools (generate_sql_economic, "
    "generate_sql_health), o modelo chama uma ou as duas na mesma resposta conforme a pergunta exigir. "
    "Continua em 2 round-trips (gera SQL + responde), como no experimento original.",
    "MCP-multi: 4 tools descobertas dinamicamente (get_economic_schema, query_economic_indicators, "
    "get_health_schema, query_health_indicators); o agente só busca o schema da fonte que realmente vai usar.",
    "",
    "15 perguntas: 5 só-econômicas, 5 só-saúde, 5 cruzando as duas fontes (categoria na aba Perguntas-Multi).",
    "Cada pergunta roda em sessão isolada (sem contexto persistente entre perguntas — a variável sob teste "
    "aqui é o Nº DE FONTES, não persistência de contexto, já testada à parte no MCP-Contexto).",
    "",
    "RESULTADO: ao contrário da hipótese, o REST-multi continuou mais rápido e mais barato que o MCP-multi "
    "em TODAS as categorias, inclusive nas de fonte única (onde a hipótese previa que o REST pagaria um "
    "pedágio por carregar um schema que não usa). O custo do MCP vem mais do processo iterativo em si "
    "(descoberta de schema + eventuais tentativas repetidas de query) do que do tamanho do prompt — e com "
    "só 2 fontes de schema compacto, esse custo de processo pesou mais que a economia de prompt do MCP. "
    "Isso não confirma nem refuta a hipótese para um número maior de fontes ou schemas maiores — permanece "
    "como limitação/trabalho futuro.",
    "",
    "Nota metodológica: a tabela de saúde inicialmente só tinha country_code (sem nome do país), o que fez o "
    "REST (sem chance de tentar de novo) chutar o formato errado do código em 4 das 5 perguntas de saúde e "
    "devolver 'sem dados' silenciosamente, mesmo com o dado existindo — enquanto o MCP se recuperava do "
    "mesmo erro por poder tentar de novo. Esse viés de schema assimétrico foi corrigido (nome do país "
    "adicionado de volta) e a bateria foi refeita antes destes resultados serem gerados — os números aqui "
    "já são da versão corrigida, 15/15 sucesso nos dois lados.",
    "",
    "Células com fundo amarelo = dados brutos da coleta. O resto é fórmula.",
]
for idx, line in enumerate(notes, start=2):
    c = ws.cell(row=idx, column=1, value=line)
    c.font = NOTE_FONT if line and not line.endswith(":") else Font(name=FONT_NAME, bold=True)
    c.alignment = Alignment(wrap_text=True)

# ------------------------------------------------------------- Perguntas-Multi
ws = wb.create_sheet("Perguntas-Multi")
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

# --------------------------------------------------------- REST-Multi / MCP-Multi
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
        # fontes_usadas
        cell = ws.cell(row=row, column=col)
        cell.value = ", ".join(result.get("sources_used", [])) or ""
        cell.fill = INPUT_FILL
        col += 1
        # erro
        if not result.get("_ok", False):
            ws.cell(row=row, column=col, value=str(result.get("_error", "erro desconhecido"))[:300])

    ws.freeze_panes = "D2"
    ws.column_dimensions["A"].width = 5
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 60
    for j in range(4, 4 + len(metric_headers)):
        ws.column_dimensions[get_column_letter(j)].width = 17
    return ws


build_impl_sheet("REST-Multi", is_mcp=False, log_key="rest_multi")
build_impl_sheet("MCP-Multi", is_mcp=True, log_key="mcp_multi")

# Colunas fixas (pela ordem de BASE_METRIC_COLS), a partir de D:
# D=total_latency_ms E=llm_round_trips F=tool_call_count G=sources_used_count
# H=input_tokens I=output_tokens J=rows_returned K=request_bytes L=response_bytes
# M=llm_bytes_sent N=llm_bytes_received O=mcp_bytes_sent P=mcp_bytes_received
# Q=db_payload_bytes R=fontes_usadas S=erro

# ------------------------------------------------------------- Comparativo-Multi
ws = wb.create_sheet("Comparativo-Multi")
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


REST = "'REST-Multi'"
MCP = "'MCP-Multi'"

for i in range(1, 16):
    row = i + 1
    ws.cell(row=row, column=1, value=f"='Perguntas-Multi'!A{row}")
    ws.cell(row=row, column=2, value=f"='Perguntas-Multi'!B{row}")
    ws.cell(row=row, column=3, value=f"='Perguntas-Multi'!C{row}")
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

# ------------------------------------------------------------------ Resumo-Multi
ws = wb.create_sheet("Resumo-Multi")
ws["A1"] = "Resumo por categoria (médias) — calculado por fórmula a partir da aba Comparativo-Multi"
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

# Colunas da aba Comparativo-Multi usadas: D/E=lat, F/G=rt, I/J... espera,
# vamos usar diretamente as letras corretas conforme comp_headers acima:
# D=Lat REST E=Lat MCP | F=RT REST G=RT MCP | I=Tok REST J=Tok MCP
# K=BytesLLM REST L=BytesLLM MCP | N=Linhas REST O=Linhas MCP
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
    crit = f"'Comparativo-Multi'!$B$2:$B$16,\"{cat}\""
    col = 2
    for key in ("lat", "rt", "tok", "bytes", "linhas"):
        fmt = "0.00" if key == "lat" else ("0.0" if key == "rt" else ("0" if key == "tok" else ("#,##0" if key == "bytes" else "0.0")))
        for letter in COMP_COLS[key]:
            if cat == "Total":
                formula = f"=IFERROR(AVERAGE('Comparativo-Multi'!${letter}$2:${letter}$16),\"\")"
            else:
                formula = f"=IFERROR(AVERAGEIFS('Comparativo-Multi'!${letter}$2:${letter}$16,{crit}),\"\")"
            ws.cell(row=row, column=col, value=formula).number_format = fmt
            col += 1
    if cat == "Total":
        ws.cell(row=row, column=col, value="=COUNTA('Comparativo-Multi'!$B$2:$B$16)")
    else:
        ws.cell(row=row, column=col, value=f"=COUNTIF('Comparativo-Multi'!$B$2:$B$16,\"{cat}\")")

ws.column_dimensions["A"].width = 14
for j in range(2, len(resumo_headers) + 1):
    ws.column_dimensions[get_column_letter(j)].width = 20

wb.save(IN_OUT_PATH)
print("Abas de multisource adicionadas a", IN_OUT_PATH)
print("Sheets:", wb.sheetnames)
