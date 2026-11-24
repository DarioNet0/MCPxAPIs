"""Gera os gráficos comparativos do capítulo de resultados do TCC a partir
dos valores já calculados por fórmula em resultados_side_by_side.xlsx
(abas Resumo / Resumo-Multi / Resumo-Json). Nenhum número é inventado
aqui -- tudo vem direto da planilha consolidada a partir dos logs reais.
"""
import openpyxl
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

OUT = Path("results/charts")
OUT.mkdir(exist_ok=True)

# Paleta consistente com o padrão visual já usado na planilha (header azul 1F4E78)
C_REST = "#1F4E78"
C_MCP_TRAD = "#C55A11"
C_MCP_CTX = "#548235"
C_MCP = "#C55A11"

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.alpha": 0.25,
    "figure.dpi": 150,
})

wb = openpyxl.load_workbook("results/resultados_side_by_side.xlsx", data_only=True)


def rows(sheet_name, n, start_row=3):
    ws = wb[sheet_name]
    data = {}
    for r in ws.iter_rows(min_row=start_row, max_row=start_row + n - 1, values_only=True):
        data[r[0]] = r[1:]
    return data


def bar_labels(ax, bars, fmt="{:.0f}"):
    for b in bars:
        h = b.get_height()
        ax.annotate(fmt.format(h), (b.get_x() + b.get_width() / 2, h),
                     ha="center", va="bottom", fontsize=8.5, xytext=(0, 2),
                     textcoords="offset points")


# ---------------------------------------------------------------------
# Fig 1 e 2: bateria principal (REST x MCP-Tradicional x MCP-Contexto)
# ---------------------------------------------------------------------
main = rows("Resumo", 4, start_row=4)  # Fácil, Média, Difícil, Total
cats = ["Fácil", "Média", "Difícil"]
x = np.arange(len(cats))
w = 0.26

# Latência (colunas 0,1,2 = REST, MCP-Trad, MCP-Ctx em ms -> converter p/ s)
fig, ax = plt.subplots(figsize=(7.5, 4.5))
rest = [main[c][0] / 1000 for c in cats]
trad = [main[c][1] / 1000 for c in cats]
ctx = [main[c][2] / 1000 for c in cats]
b1 = ax.bar(x - w, rest, w, label="REST", color=C_REST)
b2 = ax.bar(x, trad, w, label="MCP-Tradicional", color=C_MCP_TRAD)
b3 = ax.bar(x + w, ctx, w, label="MCP-Contexto", color=C_MCP_CTX)
bar_labels(ax, b1, "{:.1f}")
bar_labels(ax, b2, "{:.1f}")
bar_labels(ax, b3, "{:.1f}")
ax.set_xticks(x)
ax.set_xticklabels(cats)
ax.set_ylabel("Latência média (s)")
ax.set_title("Experimento principal — latência média por categoria de pergunta")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUT / "fig1_latencia_principal.png")
plt.close(fig)

# Tokens
fig, ax = plt.subplots(figsize=(7.5, 4.5))
rest = [main[c][6] for c in cats]
trad = [main[c][7] for c in cats]
ctx = [main[c][8] for c in cats]
b1 = ax.bar(x - w, rest, w, label="REST", color=C_REST)
b2 = ax.bar(x, trad, w, label="MCP-Tradicional", color=C_MCP_TRAD)
b3 = ax.bar(x + w, ctx, w, label="MCP-Contexto", color=C_MCP_CTX)
bar_labels(ax, b1)
bar_labels(ax, b2)
bar_labels(ax, b3)
ax.set_xticks(x)
ax.set_xticklabels(cats)
ax.set_ylabel("Tokens médios (entrada + saída)")
ax.set_title("Experimento principal — consumo médio de tokens por categoria")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUT / "fig2_tokens_principal.png")
plt.close(fig)

# ---------------------------------------------------------------------
# Fig 3 e 4: multi-fonte e sem-SQL (REST x MCP), latência por categoria
# ---------------------------------------------------------------------
def fig_rest_mcp(sheet, fname, title, ylabel, col_idx, div=1, fmt="{:.1f}"):
    data = rows(sheet, 3, start_row=4)  # Econômico, Saúde, Cruzado
    cats2 = ["Econômico", "Saúde", "Cruzado"]
    x2 = np.arange(len(cats2))
    w2 = 0.32
    fig, ax = plt.subplots(figsize=(7, 4.5))
    rest_v = [data[c][col_idx] / div for c in cats2]
    mcp_v = [data[c][col_idx + 1] / div for c in cats2]
    b1 = ax.bar(x2 - w2 / 2, rest_v, w2, label="REST", color=C_REST)
    b2 = ax.bar(x2 + w2 / 2, mcp_v, w2, label="MCP", color=C_MCP)
    bar_labels(ax, b1, fmt)
    bar_labels(ax, b2, fmt)
    ax.set_xticks(x2)
    ax.set_xticklabels(cats2)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(OUT / fname)
    plt.close(fig)


fig_rest_mcp("Resumo-Multi", "fig3_latencia_multi.png",
             "Experimento multi-fonte — latência média por categoria",
             "Latência média (s)", col_idx=0, div=1000, fmt="{:.1f}")

fig_rest_mcp("Resumo-Json", "fig4_latencia_json.png",
             "Experimento sem SQL — latência média por categoria",
             "Latência média (s)", col_idx=0, div=1000, fmt="{:.1f}")

# ---------------------------------------------------------------------
# Fig 5: evolução do overhead do MCP (REST=baseline 0%) — latência,
# tokens e bytes, comparando as três variantes do experimento
# secundário: MCP-Tradicional (bateria principal), Multi-fonte (com
# SQL) e Sem-SQL/JSON
# ---------------------------------------------------------------------
main_tot = main["Total"]
multi_tot = rows("Resumo-Multi", 4, start_row=4)["Total"]
json_tot = rows("Resumo-Json", 4, start_row=4)["Total"]


def pct_overhead(rest_v, mcp_v):
    return (mcp_v - rest_v) / rest_v * 100


scenarios = ["MCP-Tradicional\n(bateria principal)", "Multi-fonte\n(com SQL)", "Sem SQL\n(JSON)"]
lat_over = [
    pct_overhead(main_tot[0], main_tot[1]),
    pct_overhead(multi_tot[0], multi_tot[1]),
    pct_overhead(json_tot[0], json_tot[1]),
]
tok_over = [
    pct_overhead(main_tot[6], main_tot[7]),
    pct_overhead(multi_tot[4], multi_tot[5]),
    pct_overhead(json_tot[4], json_tot[5]),
]
bytes_over = [
    pct_overhead(main_tot[9], main_tot[10]),
    pct_overhead(multi_tot[6], multi_tot[7]),
    pct_overhead(json_tot[6], json_tot[7]),
]

x3 = np.arange(len(scenarios))
w3 = 0.26
fig, ax = plt.subplots(figsize=(8.5, 5))
ax.axhline(0, color="#444", linewidth=1)
b1 = ax.bar(x3 - w3, lat_over, w3, label="Latência", color=C_REST)
b2 = ax.bar(x3, tok_over, w3, label="Tokens", color=C_MCP_TRAD)
b3 = ax.bar(x3 + w3, bytes_over, w3, label="Bytes (LLM)", color=C_MCP_CTX)
bar_labels(ax, b1, "{:+.0f}%")
bar_labels(ax, b2, "{:+.0f}%")
bar_labels(ax, b3, "{:+.0f}%")
ax.set_xticks(x3)
ax.set_xticklabels(scenarios)
ax.set_ylabel("Overhead do MCP em relação ao REST (%)")
ax.set_title("Evolução do overhead do MCP conforme a arquitetura de\nconsulta muda (REST = linha de base 0%)")
ax.legend(frameon=False)
fig.tight_layout()
fig.savefig(OUT / "fig5_evolucao_overhead.png")
plt.close(fig)

print("Gráficos gerados em", OUT.resolve())
for f in sorted(OUT.glob("*.png")):
    print(" -", f.name)

print("\nValores de overhead (%) usados na fig5:")
print("cenario, latencia, tokens, bytes")
for s, l, t, b in zip(scenarios, lat_over, tok_over, bytes_over):
    print(s.replace("\n", " "), round(l, 1), round(t, 1), round(b, 1))
