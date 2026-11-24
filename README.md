# MCP Server vs. REST API: What Changes?

Experimental case study from my undergraduate thesis in Information Systems
(Universidade do Planalto de Araxá — Uniaraxá, 2026, approved).

It compares two ways of giving an LLM access to data: a **conventional REST API**
and a **Model Context Protocol (MCP) server**. Both implement the same feature —
answering natural-language questions about global macroeconomic indicators by
querying a database and generating a contextualized answer with an LLM
(Claude Haiku) — so they can be compared on architecture, performance, and security.

## Key results

| | REST | MCP (new session per question) | MCP (continuous session) |
|---|---|---|---|
| Success rate (30 questions) | 96.7% | 86.7% | **100%** |
| Cost per question | baseline | higher | **~8x REST** |

- **REST was faster and cheaper** in almost every scenario tested.
- **MCP was more robust:** best success rate in continuous sessions, and it recovered
  from data ambiguities that made REST fail silently in the multi-source experiment.
- **Most of MCP's latency overhead comes from SQL generation, not the protocol.**
  Without SQL generation, the gap went from +34% to -2%. But because tool definitions
  are resent every agent round, MCP still used ~53% more tokens and ~41% more bytes.
- **Security was a tie:** 0 violations in 24 adversarial runs (12 prompts × 2 architectures).
  The effective defense came mostly from the model's alignment, not the validation layer.
- **MCP was not simpler to build here:** ~23% more lines of code, because the agent
  loop that REST keeps inside the server has to be written as a separate MCP client.

**Takeaway:** choosing between MCP and REST is a trade-off between
performance/cost and robustness/flexibility — not a case of one being simply better.

## Repository structure

```
rest-api/        REST implementation (FastAPI). Fixed flow: 2 LLM calls (question → SQL, data → answer).
                 The database schema is embedded in the system prompt. Stateless.
mcp-server/      MCP implementation (official Python SDK, stdio transport). The client discovers
                 tools dynamically (list_tools) and Claude decides when and how often to call them.
experiments/     Scripts that ran the thesis experiments:
                   runner.py            main experiment — 30 questions × REST and MCP (new session)
                   run_mcp_contexto.py  same 30 questions in ONE continuous MCP session
                   multisource_runner.py  multi-source experiment (economic + health databases)
                   json_runner.py       experiment without SQL generation (isolates protocol overhead)
                   security_runner.py   12 adversarial prompts × 2 architectures
                   side_by_side.py      runs a single question on both and compares metrics
                   questions/           question sets used in the experiments
analysis/        Scripts that turn the raw logs into the results workbook and charts.
results/         Raw JSONL logs of every run, the results workbook, and the charts used in the thesis.
data/health/     Schema of the health indicators database (multi-source experiment).
docs/            Test questions, metric definitions, and preliminary notes.
```

Both implementations validate every LLM-generated query before execution
(single `SELECT` only, no destructive keywords), as a guard against prompt/SQL injection.

**Metrics collected:** total latency, LLM round-trips, input/output tokens,
message size (bytes), dollar cost, and implementation complexity (lines of code, files).

## Data

[Global Economic Indicators 2010–2025 – World Bank](https://www.kaggle.com/) (Kaggle):
GDP, inflation, unemployment, real interest rate, public debt, government
revenue/expenses, current account balance, GNI, and tax revenue by country, continent, and year.
Loaded into SQLite.

## Tech stack

Python · FastAPI · MCP Python SDK · Anthropic API (Claude Haiku) · SQLite · pytest

## How to run

> **Important:** `rest-api` and `mcp-server` must run in **separate virtual environments** —
> the MCP SDK and FastAPI depend on incompatible versions of `starlette`.

Each folder has its own README with full setup steps. In short:

```bash
# REST API
cd rest-api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY
python data/load_data.py path/to/dataset.csv
uvicorn app.main:app --port 8000

# MCP server (in another terminal)
cd mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY
python data/load_data.py path/to/dataset.csv

# Compare both on one question (run from the repo root)
python experiments/side_by_side.py "What was the average GDP growth in South America in 2023?"

# Full experiments and analysis (run from the repo root)
python experiments/runner.py
python analysis/generate_charts.py
```

Tests mock all LLM calls, so they don't use API credits:

```bash
pytest -v
```

---

🇧🇷 *Versão em português:* este repositório contém o estudo de caso do TCC
"MCP Server x API REST: O Que Muda?" (Sistemas de Informação — Uniaraxá, 2026).
Os READMEs de `rest-api/` e `mcp-server/` trazem as instruções detalhadas em português.
