-- Schema: economic_indicators
-- Formato "wide": uma linha por país/ano, uma coluna por indicador.
-- Baseado no dataset Kaggle "Global Economic Indicators 2010-2025 - World Bank".

CREATE TABLE IF NOT EXISTS economic_indicators (
    id                                  INTEGER PRIMARY KEY AUTOINCREMENT,
    country                             TEXT NOT NULL,
    country_code                        TEXT,
    continent                           TEXT,
    year                                INTEGER NOT NULL,
    gdp_usd                             REAL,
    gdp_growth_pct                      REAL,
    inflation_cpi_pct                   REAL,
    unemployment_rate_pct               REAL,
    real_interest_rate_pct              REAL,
    government_debt_pct_gdp             REAL,
    government_revenue_pct_gdp          REAL,
    government_expense_pct_gdp          REAL,
    current_account_balance_pct_gdp     REAL,
    gni_usd                             REAL,
    tax_revenue_pct_gdp                 REAL,
    UNIQUE(country, year)
);

CREATE INDEX IF NOT EXISTS idx_ei_country ON economic_indicators(country);
CREATE INDEX IF NOT EXISTS idx_ei_continent ON economic_indicators(continent);
CREATE INDEX IF NOT EXISTS idx_ei_year ON economic_indicators(year);
