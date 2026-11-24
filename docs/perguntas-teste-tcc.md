# Perguntas de teste — REST x MCP (30 perguntas)

> Rascunho proposto em 10/09/2026. Estrutura: 10 fáceis (consultas diretas),
> 10 médias (cruzamento de indicadores), 10 difíceis (cruzamento +
> tentativa de previsão). Ainda não confirmado como lista final.

## Fáceis — consultas diretas (10)

1. Qual foi a média de crescimento do PIB da Europa em 2023?
2. Qual país teve a maior taxa de desemprego em 2015?
3. Qual foi a inflação média da Ásia entre 2020 e 2022?
4. Qual país teve a menor dívida pública (% do PIB) em 2024?
5. Quais os 5 países com maior RNB (Gross National Income) em 2021?
6. Qual foi a taxa de juros real média da África em 2018?
7. Qual país teve o maior saldo em conta corrente em 2022?
8. Qual foi a receita tributária média dos países da América do Norte em 2019?
9. Qual foi o crescimento do PIB do Brasil em 2020?
10. Quais os 3 países com menor taxa de desemprego na Oceania em 2023?

## Médias — cruzamento de indicadores (10)

11. Existe correlação entre crescimento do PIB e taxa de desemprego na Europa entre 2010 e 2025?
12. Como a dívida pública se relaciona com a taxa de juros real nos países da América do Sul?
13. Os países com maior inflação também tiveram menor crescimento do PIB em 2022?
14. Qual a relação entre despesa do governo e receita tributária nos países da Ásia na última década?
15. O saldo em conta corrente acompanha o crescimento do RNB nos países da Oceania?
16. Como o desemprego evoluiu em relação à dívida pública na América do Norte entre 2015 e 2020?
17. Existe relação entre taxa de juros real e crescimento do PIB nos países emergentes (fora do G7)?
18. Países com maior receita tributária têm menor dívida pública, em média, na Europa?
19. Qual a relação entre inflação e taxa de juros real nos países da América Latina entre 2018 e 2023?
20. Como a despesa do governo se comportou em relação ao crescimento do PIB durante a pandemia (2020–2021), globalmente?

## Difíceis — cruzamento + tentativa de previsão (10)

21. Com base na tendência de crescimento do PIB da Índia nos últimos 10 anos, qual seria a projeção para 2026?
22. Considerando a trajetória da dívida pública do Brasil desde 2015, ela deve continuar subindo, estabilizar ou cair nos próximos anos?
23. Dado o histórico de inflação e desemprego da Argentina entre 2010 e 2025, qual a tendência esperada para os próximos dois anos?
24. Com base na relação histórica entre despesa do governo e receita tributária na Zona do Euro, o déficit fiscal tende a aumentar ou diminuir?
25. Analisando a evolução da taxa de juros real e do crescimento do PIB nos EUA, existe algum padrão que sugira o que aconteceria com uma alta adicional de juros?
26. Qual seria a estimativa de crescimento do RNB per capita da China para os próximos 3 anos, com base na série histórica?
27. Considerando a relação entre saldo em conta corrente e crescimento do PIB dos países exportadores de commodities (ex: Austrália, Canadá, Brasil), o que se pode prever sobre o impacto de uma queda nos preços de commodities?
28. Com base no padrão histórico de crescimento do PIB e evolução do desemprego no Japão, a economia japonesa tende a acelerar ou desacelerar nos próximos anos?
29. Dada a correlação entre dívida pública e taxa de juros real observada nos países da União Europeia, o que se pode esperar se os juros subirem mais 2 pontos percentuais?
30. Considerando a tendência combinada de inflação, desemprego e crescimento do PIB dos BRICS na última década, esses países estão convergindo ou divergindo economicamente?

## Nota metodológica

O bloco "difíceis" é o mais interessante para o capítulo de resultados:
pedir previsão/tendência força o LLM a raciocinar sobre uma série temporal
(múltiplos anos, não um único valor agregado), o que deve acentuar as
diferenças já observadas no teste preliminar de 23/08 — mais rounds de
consulta, mais linhas cruas retornadas, mais tokens gastos "pensando" sobre
os dados antes de responder. Esse bloco é onde a vantagem teórica do MCP
(contexto persistente dentro de uma sessão) tem mais chance de aparecer,
já que uma previsão bem feita provavelmente exige puxar dados de vários
anos em sequência.
