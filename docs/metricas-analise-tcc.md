# Métricas de análise — REST x MCP

> Atualizado em 10/09/2026. Instrumentação de bytes (request/response,
> LLM, MCP, dados) adicionada nesta data em `rest-api/app/llm.py`,
> `rest-api/app/main.py`, `mcp-server/client.py` e `experiments/side_by_side.py`.
> Todo campo listado abaixo já está sendo coletado automaticamente em
> `metrics` (REST) ou `metrics` (MCP), salvo indicação contrária.

## 1. Desempenho — coletadas automaticamente

| Métrica | Campo | REST | MCP | O que revela |
|---|---|---|---|---|
| Latência total | `total_latency_ms` | ✅ | ✅ | Tempo fim-a-fim por pergunta |
| Round-trips ao LLM | `llm_round_trips` | ✅ (fixo = 2) | ✅ (variável) | REST tem fluxo fixo; MCP decide dinamicamente |
| Chamadas de tool | `tool_call_count` | — (sem equivalente; 1 chamada REST ≈ 1 "tool call" implícita) | ✅ | Quantas vezes o agente MCP acessou o backend |
| Tokens de entrada/saída | `input_tokens` / `output_tokens` | ✅ | ✅ | Custo computacional de contexto |
| Linhas retornadas do banco | `rows_returned` | ✅ | ✅ | Se a estratégia de query foi agregada (poucas linhas) ou crua (muitas linhas) |
| Latência por etapa | `sql_generation_latency_ms`, `sql_execution_latency_ms`, `answer_generation_latency_ms` | ✅ | parcial (`last_llm_call_latency_ms`) | Onde o tempo é gasto dentro do fluxo REST; MCP não tem etapas fixas para decompor da mesma forma |

## 2. Tamanho de payload (bytes) — instrumentado em 10/09/2026

| Métrica | Campo | REST | MCP | O que revela |
|---|---|---|---|---|
| Payload externo de entrada | `request_bytes` | ✅ (corpo HTTP de `/query`) | ✅ (pergunta em bytes) | Tamanho do que o cliente final envia |
| Payload externo de saída | `response_bytes` | ✅ | ✅ | Tamanho do que o cliente final recebe (sem contar o próprio bloco de metrics, pra evitar circularidade) |
| Bytes trocados com o LLM | `llm_bytes_sent` / `llm_bytes_received` | ✅ (soma das 2 chamadas) | ✅ (soma de todos os round-trips) | Overhead de protocolo visível ao modelo — inclui system prompt, schema de tools e histórico de mensagens |
| Bytes trocados MCP↔servidor | `mcp_bytes_sent` / `mcp_bytes_received` | — (não existe; a consulta ao banco é uma chamada de função no mesmo processo, não uma mensagem de protocolo) | ✅ | Overhead específico do transporte stdio do MCP — não tem equivalente direto no REST, mas é o número que sustenta a discussão de "MCP tem uma camada de protocolo a mais" |
| Payload de dados brutos | `db_payload_bytes` | ✅ (JSON das linhas antes do round-trip de resposta) | ✅ (soma dos resultados de `query_economic_indicators`) | Volume de dados brutos movidos — mesmo critério nos dois lados, então é comparável de forma justa |

## 3. Custo estimado — derivável sem instrumentar nada

Não precisa mudar código: já que `input_tokens`/`output_tokens` são coletados, dá pra calcular custo em USD na hora da análise usando a tabela de preços do Claude Haiku vigente na época da coleta (documentar a tabela usada, porque preços mudam).

## 4. Robustez / taxa de erro — coletar durante a bateria de testes

Não é um campo automático hoje — precisa ser registrado manualmente (ou por um wrapper no `side_by_side.py`) durante a rodada formal de setembro:

- Quantas perguntas estouraram `MAX_AGENT_STEPS = 6` no MCP (erro `RuntimeError`)
- Quantas tiveram SQL rejeitado pela validação de segurança (`UnsafeQueryError` no REST / `{"error": ...}` no MCP)
- Quantas deram timeout ou erro de rede

## 5. Qualidade da resposta — avaliação manual, principalmente no bloco "difícil"

Sem critério objetivo de corretude hoje. Proposta mínima antes de rodar a bateria formal:

- **Fáceis/médias**: comparar a resposta contra o valor esperado calculado manualmente a partir do dataset (é verificável).
- **Difíceis (previsão)**: não existe "resposta certa" — usar um checklist simples por resposta (ex.: 1 a 5 em cada item): usou os dados históricos corretos? foi transparente sobre incerteza/limitação da extrapolação? não inventou números que não estão no dataset?

## 6. Complexidade de implementação — qualitativa, sustentada por números do repo

- Linhas de código e nº de arquivos por implementação (`rest-api/app` vs `mcp-server/app`)
- Acoplamento cliente-servidor: REST precisa do schema fixo embutido no system prompt (`llm.py`); MCP descobre via `list_tools()` em tempo de execução — mais resiliente a mudanças de schema, mas com custo de descoberta
- Dependências e ambientes: REST e MCP precisam de venvs Python separados (conflito de versão do `starlette` entre FastAPI e o SDK do MCP) — isso em si é um ponto de complexidade operacional a citar

## 7. Perguntas metodológicas em aberto (do teste preliminar de 23/08)

Tratar como hipóteses formais a testar na bateria de setembro, não como métricas de coleta direta:

1. O custo de descoberta de schema do MCP (`get_database_schema`) se amortiza numa sessão com várias perguntas em sequência? O `client.py` atual não testa isso (cada invocação é uma sessão nova) — precisaria de uma variante do script que mantenha uma sessão entre perguntas.
2. A diferença de tokens/latência é do protocolo ou da estratégia de prompt (REST direciona pra SQL agregado, MCP é mais "livre")? Testável rodando uma variante do MCP com prompt mais diretivo e comparando.

## 8. Segurança (ligada ao referencial teórico)

Não faz parte das 30 perguntas do experimento principal, mas vale um pequeno conjunto separado de prompts adversariais (tentativas de prompt injection / SQL injection via linguagem natural) para gerar uma métrica binária: taxa de rejeição correta pela camada de validação (`UnsafeQueryError` / tool retornando erro) em cada implementação. Sustenta o capítulo de segurança do referencial teórico com dado empírico, não só teoria.
