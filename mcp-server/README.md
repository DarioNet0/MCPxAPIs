# MCP Server — Estudo de Caso (TCC: MCP x APIs Convencionais)

Implementação MCP do estudo de caso comparativo. Mesma funcionalidade da
implementação REST (consulta a indicadores macroeconômicos globais +
resposta contextualizada por LLM), só que via Model Context Protocol:

- O servidor (`app/server.py`) expõe **tools** via transporte stdio —
  não tem endpoint HTTP, não tem rota, é um processo local que fala o
  protocolo MCP na entrada/saída padrão.
- O cliente/agente (`client.py`) conecta no servidor, **descobre as tools
  dinamicamente** (`list_tools()` — nada de schema hardcoded), e deixa o
  próprio Claude decidir quando e quantas vezes chamar cada tool dentro de
  uma sessão com estado, até ter dados suficientes pra responder.

Isso contrasta com o REST, onde o backend orquestra uma sequência **fixa**
de 2 chamadas ao LLM (NL→SQL, dados→resposta) e o schema do banco vem
embutido no system prompt.

## Setup

**Importante:** use um ambiente virtual **separado** do `rest-api`. O SDK
do MCP puxa uma versão do `starlette` incompatível com o `fastapi` da
implementação REST — instalar os dois no mesmo ambiente pode quebrar um
dos dois.

```bash
cd mcp-server
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# edite .env e cole sua ANTHROPIC_API_KEY (pode ser a mesma do REST)
```

## Carregar o dataset

```bash
python data/load_data.py caminho/para/world_bank_data_2025.csv
```

Mesmo CSV, mesmo schema, mesma lógica de ETL da implementação REST — só
que gera um `.db` próprio (`data/economic_indicators.db`), pra manter os
dois cenários completamente independentes na infraestrutura, mas com
dados idênticos.

## Rodar

**Testar o cliente isoladamente** (sobe o servidor como subprocesso
automaticamente):

```bash
python client.py "Qual foi a média de crescimento do PIB da América do Sul em 2023?"
```

Devolve um JSON com a resposta, as tools chamadas pelo agente e as
métricas (latência, round-trips ao LLM, tokens, linhas retornadas).

**Rodar o servidor sozinho** (útil pra depurar o protocolo MCP com o
MCP Inspector, por exemplo):

```bash
python -m app.server
```

## Testes

```bash
pytest -v
```

Cobre: as tools chamadas diretamente, um round-trip real do protocolo MCP
via stdio (subprocesso de verdade, sem precisar do LLM), e o loop do
agente com a chamada à Anthropic mockada (mas a comunicação MCP e a
consulta ao SQLite são reais).

## Segurança

Mesma barreira do REST: `app/db.py` só aceita `SELECT` puro vindo da tool
`query_economic_indicators` (sem `DROP`/`DELETE`/`INSERT`/etc., sem múltiplas
instruções). A diferença para o capítulo de segurança do TCC é que aqui a
superfície de ataque é a própria tool exposta ao modelo — o MCP dá ao LLM
acesso mais direto a "ferramentas" do sistema, então a validação dentro da
tool é a única linha de defesa (não há uma camada HTTP intermediária).

## Comparando com o REST

Veja `../scripts/side_by_side.py` na raiz do repositório — roda a mesma
pergunta nos dois cenários e compara latência, round-trips e tokens lado a
lado.
