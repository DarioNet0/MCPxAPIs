-- Schema: health_indicators
-- Fonte: World Bank Open Data API (api.worldbank.org), indicadores
-- SP.DYN.LE00.IN (expectativa de vida ao nascer), SH.XPD.CHEX.GD.ZS
-- (despesa corrente em saúde, % do PIB) e SP.DYN.IMRT.IN (mortalidade
-- infantil, por 1.000 nascidos vivos). Uma linha por país/ano.
--
-- Banco SEPARADO de economic_indicators (arquivo .db diferente) --
-- representa uma segunda fonte de dados heterogênea, sem possibilidade
-- de JOIN via SQL (ATTACH é proibido pela mesma regra de segurança
-- usada no restante do projeto). O cruzamento entre as duas fontes só
-- pode ser feito combinando o resultado de duas consultas separadas,
-- usando country_code + year como chave comum.

CREATE TABLE IF NOT EXISTS health_indicators (
    id                            INTEGER PRIMARY KEY AUTOINCREMENT,
    country_code                  TEXT NOT NULL,
    country                       TEXT,
    year                          INTEGER NOT NULL,
    life_expectancy_years         REAL,
    health_expenditure_pct_gdp    REAL,
    infant_mortality_rate         REAL,
    UNIQUE(country_code, year)
);

CREATE INDEX IF NOT EXISTS idx_hi_country_code ON health_indicators(country_code);
CREATE INDEX IF NOT EXISTS idx_hi_year ON health_indicators(year);
