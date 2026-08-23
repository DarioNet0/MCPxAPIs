# Notas preliminares — REST x MCP (desempenho)

> Registrado em 23/08/2026, no primeiro teste lado a lado dos dois cenários.
> **Um único ponto de dado — não é conclusão, é hipótese a testar
> formalmente em setembro com a bateria completa de perguntas.**

## O teste

Mesma pergunta, mesmo banco (dataset World Bank carregado nos dois lados):

> "Qual foi a média de crescimento do PIB da América do Sul em 2023?"

| | REST | MCP |
|---|---|---|
| Latência total | 3.605,81 ms | 21.071,89 ms |
| Round-trips ao LLM | 2 | 3 |
| Tokens (in/out) | 1.324 / 275 | 4.168 / 509 |
| Linhas retornadas do banco | 1 (já agregada) | 12 (linhas cruas) |
| SQL gerado | `SELECT AVG(gdp_growth_pct) ...` | `SELECT country, continent, gdp_growth_pct ... ORDER BY country` |

## Por que a diferença — duas causas distintas

**1. Round-trip extra de descoberta de schema (estrutural).**
O MCP fez uma chamada a mais (`get_database_schema`) antes de consultar os
dados, porque cada execução do `client.py` inicia uma sessão nova e
isolada — sem estado entre perguntas. O REST não paga esse custo porque o
schema já vem fixo no system prompt, em toda chamada.

Isso é uma faca de dois gumes: o MCP paga esse custo de descoberta uma vez
por *sessão*, não por pergunta. Numa sessão que respondesse várias
perguntas em sequência (mantendo o contexto), a descoberta aconteceria só
na primeira, e as seguintes ficariam mais baratas que o REST — que reenvia
o schema completo no prompt a cada chamada, sempre. **A implementação
atual do client.py não testa esse cenário** (cada invocação = sessão nova).
Isso é uma limitação do *desenho do experimento*, não do protocolo MCP em
si, e deveria virar um teste específico: "pergunta isolada" vs "sequência
de perguntas na mesma sessão".

**2. Estratégia de query diferente (confound, não é o protocolo).**
O REST gerou uma query já agregada (`AVG(...)`, 1 linha). O MCP trouxe as
12 linhas cruas e fez a média "na mão", em texto, durante a resposta final
— por isso ele até comentou sobre excluir o outlier (Guyana, 33,8%) do
cálculo. Isso explica a maior parte da diferença de tokens e de latência
da última chamada ao LLM.

Isso não é uma diferença inerente ao MCP — é o system prompt do MCP sendo
menos diretivo sobre usar agregação SQL do que o do REST. Antes de
concluir que "MCP gera mais tokens", vale equalizar os prompts dos dois
lados e rodar de novo, pra isolar se a diferença é do protocolo ou da
instrução dada ao agente.

## Perguntas em aberto pra investigar em setembro

- Latência/tokens por round-trip são de fato comparáveis entre REST e MCP
  quando controlamos a estratégia de query (mesma agregação SQL nos dois)?
- O custo de descoberta de schema do MCP se amortiza numa sessão com
  múltiplas perguntas (vantagem teórica do MCP: contexto persistente)?
- Vale testar duas versões do prompt do MCP: uma "livre" (como está agora)
  e uma "diretiva" (equivalente ao REST), pra separar as duas causas acima.
