"""ETL: carrega o CSV do Kaggle 'Global Economic Indicators 2010-2025 - World Bank'
para a tabela economic_indicators do SQLite.

Uso:
    python data/load_data.py caminho/para/dataset.csv

Como os nomes exatos das colunas variam entre versões do dataset no Kaggle,
o script tenta mapear automaticamente por um dicionário de aliases. Se alguma
coluna obrigatória não for encontrada, ele lista as colunas do CSV para ajuste
manual do MAPPING abaixo.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.db import init_db, get_connection  # noqa: E402

# Aliases conhecidos -> nome da coluna no nosso schema.
# Já ajustado para o CSV real "world_bank_data_2025.csv".
COLUMN_ALIASES: dict[str, list[str]] = {
    "country": ["country", "country_name", "Country", "Country Name"],
    "country_code": ["country_code", "country_id", "iso_code", "Country Code", "iso3"],
    "continent": ["continent", "region", "Continent", "Region"],
    "year": ["year", "Year"],
    "gdp_usd": ["gdp", "gdp_usd", "GDP (current US$)", "GDP", "GDP (Current USD)"],
    "gdp_growth_pct": ["gdp_growth", "gdp_growth_pct", "GDP Growth (%)", "GDP growth (annual %)", "GDP Growth (% Annual)"],
    "inflation_cpi_pct": [
        "inflation", "inflation_cpi", "Inflation (CPI %)", "Inflation, consumer prices (annual %)",
    ],
    "unemployment_rate_pct": ["unemployment", "unemployment_rate", "Unemployment Rate (%)"],
    "real_interest_rate_pct": ["real_interest_rate", "Real Interest Rate (%)", "Interest Rate (Real, %)"],
    "government_debt_pct_gdp": ["government_debt", "public_debt", "Government Debt (% of GDP)", "Public Debt (% of GDP)"],
    "government_revenue_pct_gdp": ["government_revenue", "Government Revenue (% of GDP)"],
    "government_expense_pct_gdp": ["government_expense", "government_expenditure", "Government Expense (% of GDP)"],
    "current_account_balance_pct_gdp": [
        "current_account_balance", "Current Account Balance (% of GDP)", "Current Account Balance (% GDP)",
    ],
    "gni_usd": ["gni", "gni_usd", "GNI (current US$)", "GNI", "Gross National Income (USD)"],
    "tax_revenue_pct_gdp": ["tax_revenue", "Tax Revenue (% of GDP)"],
}

REQUIRED = ["country", "year"]


def _resolve_column(df: pd.DataFrame, target: str) -> str | None:
    for alias in COLUMN_ALIASES[target]:
        if alias in df.columns:
            return alias
    return None


def _derive_continent(country_code: str | None) -> str | None:
    """Deriva o continente a partir do código ISO alpha-2 do país (quando o CSV não traz continente)."""
    if not country_code or not isinstance(country_code, str) or len(country_code) != 2:
        return None
    try:
        import pycountry_convert as pc

        code = pc.country_alpha2_to_continent_code(country_code.upper())
        return pc.convert_continent_code_to_continent_name(code)
    except Exception:
        return None


def load(csv_path: str) -> None:
    settings = get_settings()
    df = pd.read_csv(csv_path)

    resolved = {target: _resolve_column(df, target) for target in COLUMN_ALIASES}
    missing_required = [t for t in REQUIRED if resolved[t] is None]

    print("Colunas encontradas no CSV:", list(df.columns))
    print("Mapeamento resolvido:", {k: v for k, v in resolved.items() if v})

    if missing_required:
        raise SystemExit(
            f"Colunas obrigatórias não encontradas: {missing_required}. "
            "Edite COLUMN_ALIASES em data/load_data.py com os nomes reais do CSV e rode de novo."
        )

    out = pd.DataFrame()
    for target, source_col in resolved.items():
        out[target] = df[source_col] if source_col else None

    if resolved["continent"] is None and resolved["country_code"] is not None:
        out["continent"] = out["country_code"].apply(_derive_continent)
        n_unresolved = out["continent"].isna().sum()
        print(f"Continente derivado automaticamente via ISO alpha-2 ({n_unresolved} linhas sem continente resolvido).")

    out = out.dropna(subset=["country", "year"])
    out["year"] = out["year"].astype(int)

    init_db()
    with get_connection() as conn:
        conn.execute("DELETE FROM economic_indicators")
        out.to_sql("economic_indicators", conn, if_exists="append", index=False)

    print(f"Carregadas {len(out)} linhas em {settings.database_abs_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Uso: python data/load_data.py caminho/para/dataset.csv")
    load(sys.argv[1])
