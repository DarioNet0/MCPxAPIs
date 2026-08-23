# TCC — MCP Server x APIs Convencionais: O Que Muda?

Repositório do estudo de caso experimental do TCC (Sistemas de Informação —
UNIPAM). Compara, na prática, uma implementação **REST** e uma implementação
**MCP Server** da mesma funcionalidade: consulta a uma base de dados de
indicadores macroeconômicos globais + geração de resposta contextualizada
por um LLM (Claude Haiku).

## Estrutura

```
rest-api/     Implementação REST (FastAPI) — pronta
mcp-server/   Implementação MCP Server (SDK oficial, stdio) — pronta
scripts/      side_by_side.py — roda a mesma pergunta nos dois cenários e compara métricas
```

**Importante:** `rest-api` e `mcp-server` devem rodar em ambientes/venvs
Python **separados** — o SDK do MCP e o FastAPI puxam versões incompatíveis
do `starlette`.

## Domínio dos dados

Dataset "Global Economic Indicators 2010–2025 – World Bank" (Kaggle):
PIB, inflação, desemprego, taxa de juros real, dívida pública,
receita/despesa do governo, saldo em conta corrente, RNB e receita
tributária, por país/continente/ano.

## Métricas coletadas

Para cada abordagem (REST e MCP): latência de resposta, número de
round-trips, tamanho das mensagens trocadas e complexidade de implementação
— usadas nos capítulos de resultados do TCC.

Ver `rest-api/README.md` e `mcp-server/README.md` para instruções de setup
e uso, e `scripts/side_by_side.py` para rodar a comparação.
