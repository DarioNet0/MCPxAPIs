# TCC — MCP Server x APIs Convencionais: O Que Muda?

Repositório do estudo de caso experimental do TCC (Sistemas de Informação —
UNIPAM). Compara, na prática, uma implementação **REST** e uma implementação
**MCP Server** da mesma funcionalidade: consulta a uma base de dados de
indicadores macroeconômicos globais + geração de resposta contextualizada
por um LLM (Claude Haiku).

## Estrutura

```
rest-api/     Implementação REST (FastAPI) — pronta
mcp-server/   Implementação MCP Server — próxima etapa
```

## Domínio dos dados

Dataset "Global Economic Indicators 2010–2025 – World Bank" (Kaggle):
PIB, inflação, desemprego, taxa de juros real, dívida pública,
receita/despesa do governo, saldo em conta corrente, RNB e receita
tributária, por país/continente/ano.

## Métricas coletadas

Para cada abordagem (REST e MCP): latência de resposta, número de
round-trips, tamanho das mensagens trocadas e complexidade de implementação
— usadas nos capítulos de resultados do TCC.

Ver `rest-api/README.md` para instruções de setup e uso.
