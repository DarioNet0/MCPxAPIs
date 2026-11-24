# REST API — Estudo de Caso (TCC: MCP x APIs Convencionais)

Implementação REST do estudo de caso comparativo. Recebe uma pergunta em
linguagem natural sobre indicadores macroeconômicos globais, traduz para SQL
via LLM, consulta o SQLite e devolve uma resposta contextualizada — também
via LLM. Cada chamada é independente (stateless), o que é o ponto central de
comparação com a implementação MCP Server (próxima etapa do TCC).

## Setup

```bash
cd rest-api
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edite .env e cole sua ANTHROPIC_API_KEY (console.anthropic.com/settings/keys)
```

## Carregar o dataset

```bash
python data/load_data.py caminho/para/dataset.csv
```

O script tenta mapear automaticamente as colunas do CSV do Kaggle
("Global Economic Indicators 2010-2025 - World Bank") para o schema em
`app/schema.sql`. Se faltar alguma coluna obrigatória, ele lista as colunas
encontradas no CSV para você ajustar `COLUMN_ALIASES` em `data/load_data.py`.

## Rodar o servidor

```bash
uvicorn app.main:app --reload --port 8000
```

Docs interativas: http://localhost:8000/docs

## Endpoint principal

`POST /query`

```json
{
  "question": "Qual foi a média de crescimento do PIB na Europa em 2023?",
  "category": "isolated"
}
```

Resposta:

```json
{
  "question": "...",
  "sql_generated": "SELECT AVG(gdp_growth_pct) FROM economic_indicators WHERE continent = 'Europe' AND year = 2023",
  "data": [...],
  "answer": "A média de crescimento do PIB na Europa em 2023 foi de X%...",
  "metrics": {
    "total_latency_ms": 1450.2,
    "llm_round_trips": 2,
    "sql_generation_latency_ms": 620.1,
    "sql_execution_latency_ms": 3.4,
    "answer_generation_latency_ms": 810.9,
    "input_tokens": 340,
    "output_tokens": 190,
    "rows_returned": 1
  }
}
```

O objeto `metrics` é o dado bruto usado na coleta experimental do TCC
(latência, round-trips, tokens) para comparação com o MCP Server.

## Testes

```bash
pytest -v
```

Os testes mockam as chamadas ao LLM (não gastam créditos de API) e cobrem:
caminho feliz, rejeição de SQL não-SELECT (proteção contra prompt
injection/SQL injection via LLM), e ausência de API key.

## Segurança

`app/db.py` valida que toda query gerada pelo LLM é um `SELECT` puro,
sem múltiplas instruções e sem palavras-chave destrutivas (`DROP`, `DELETE`,
`INSERT`, etc.) antes de executar. Isso é relevante para o capítulo de
segurança do TCC — é o tipo de superfície de ataque que muda entre REST e
MCP (aqui, o LLM só "sugere" SQL; no MCP, ferramentas são invocadas
diretamente pelo modelo).
