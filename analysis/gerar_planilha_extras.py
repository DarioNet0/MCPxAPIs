#!/usr/bin/env python3
"""Adiciona ao workbook existente (resultados_side_by_side.xlsx) uma aba
consolidando as três pendências técnicas fechadas em 12/09/2026: custo
estimado em USD, complexidade de implementação (linhas de código reais do
repositório) e o checklist de qualidade do bloco difícil. Números batem
com os das seções 4.7-4.9 de resultados_tcc_rascunho.docx.

Aba nova: Custo-Complexidade-Qualidade. Não mexe nas abas anteriores.
"""
from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

IN_OUT_PATH = "results/resultados_side_by_side.xlsx"

FONT_NAME = "Arial"
HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(name=FONT_NAME, bold=True, color="FFFFFF")
TITLE_FONT = Font(name=FONT_NAME, bold=True, size=12)
NOTE_FONT = Font(name=FONT_NAME, italic=True, color="555555")
SECTION_FONT = Font(name=FONT_NAME, bold=True, size=12, color="1F4E78")

wb = load_workbook(IN_OUT_PATH)

SHEET_NAME = "Custo-Complexidade-Qualidade"
if SHEET_NAME in wb.sheetnames:
    del wb[SHEET_NAME]
ws = wb.create_sheet(SHEET_NAME)

ws["A1"] = "TCC — Custo estimado, complexidade de implementação e qualidade do bloco difícil"
ws["A1"].font = Font(name=FONT_NAME, bold=True, size=14)
ws["A2"] = ("Detalhamento completo e discussão na seção 4.7-4.9 de resultados_tcc_rascunho.docx. "
            "Preço do Claude Haiku 4.5 confirmado em platform.claude.com/docs em 12/09/2026 "
            "(US$1/MTok entrada, US$5/MTok saída).")
ws["A2"].font = NOTE_FONT
ws["A2"].alignment = Alignment(wrap_text=True)
for col, w in zip("ABCDEF", [24, 16, 16, 16, 16, 16]):
    ws.column_dimensions[col].width = w

row = 4
ws.cell(row=row, column=1, value="1. Custo estimado em USD").font = SECTION_FONT
row += 1
headers = ["Variante", "Tokens entrada", "Tokens saída", "Custo total (US$)", "Custo/pergunta (US$)", "Overhead vs. REST"]
for col, h in enumerate(headers, start=1):
    c = ws.cell(row=row, column=col, value=h)
    c.font = HEADER_FONT
    c.fill = HEADER_FILL
row += 1
cost_rows = [
    ["REST (principal)", 157749, 18246, 0.2490, 0.00859, "—"],
    ["MCP-Tradicional", 261451, 22105, 0.3720, 0.01431, "+67%"],
    ["MCP-Contexto", 1842037, 30846, 1.9963, 0.06654, "+675%"],
    ["REST-Multi", 64279, 6913, 0.0988, 0.00659, "—"],
    ["MCP-Multi", 147925, 8732, 0.1916, 0.01277, "+94%"],
    ["REST-Json", 51984, 7757, 0.0908, 0.00605, "—"],
    ["MCP-Json", 84108, 7187, 0.1200, 0.00800, "+32%"],
]
for r in cost_rows:
    for col, v in enumerate(r, start=1):
        ws.cell(row=row, column=col, value=v).font = Font(name=FONT_NAME)
    row += 1

row += 2
ws.cell(row=row, column=1, value="2. Complexidade de implementação (linhas de código reais, wc -l)").font = SECTION_FONT
row += 1
headers2 = ["Camada", "REST (rest-api/)", "MCP (mcp-server/)"]
for col, h in enumerate(headers2, start=1):
    c = ws.cell(row=row, column=col, value=h)
    c.font = HEADER_FONT
    c.fill = HEADER_FILL
row += 1
loc_rows = [
    ["Lógica de servidor (config/db/rotas ou tools)", "204 linhas, 3 arquivos", "147 linhas, 3 arquivos"],
    ["Orquestração do agente/LLM", "165 linhas (llm.py, embutido)", "242 linhas (client.py, separado)"],
    ["Utilitário de inspeção", "—", "42 linhas (list_tools.py)"],
    ["Carga de dados", "109 linhas", "105 linhas"],
    ["Testes", "83 linhas, 1 arquivo", "212 linhas, 3 arquivos"],
    ["Total", "607 linhas, 7 arquivos", "748 linhas, 11 arquivos"],
]
for r in loc_rows:
    for col, v in enumerate(r, start=1):
        cell = ws.cell(row=row, column=col, value=v)
        cell.font = Font(name=FONT_NAME, bold=(r[0] == "Total"))
        cell.alignment = Alignment(wrap_text=True)
    row += 1

row += 2
ws.cell(row=row, column=1, value="3. Qualidade das respostas — bloco difícil (10 perguntas)").font = SECTION_FONT
row += 1
headers3 = ["Variante", "Perguntas com sucesso", "Menções a incerteza/cenário", "Perguntas que sinalizaram limitação nos dados"]
for col, h in enumerate(headers3, start=1):
    c = ws.cell(row=row, column=col, value=h)
    c.font = HEADER_FONT
    c.fill = HEADER_FILL
row += 1
qual_rows = [
    ["REST", "10/10", 8, "5 de 10"],
    ["MCP-Tradicional", "9/10 (Q29 falhou)", 8, "1 de 9"],
    ["MCP-Contexto", "10/10", 13, "1 de 10"],
]
for r in qual_rows:
    for col, v in enumerate(r, start=1):
        ws.cell(row=row, column=col, value=v).font = Font(name=FONT_NAME)
    row += 1
row += 1
note = ("Verificação numérica: amostra (crescimento do PIB da Índia 2020, ausência de inflação da "
        "Argentina, RNB da China 2023, dívida pública do Brasil 2015-2023) 100% consistente com o "
        "banco nas três variantes — não é auditoria exaustiva de todos os números citados.")
ws.cell(row=row, column=1, value=note).font = NOTE_FONT
ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True)
ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)

wb.save(IN_OUT_PATH)
print("OK: aba", SHEET_NAME, "adicionada a", IN_OUT_PATH)
