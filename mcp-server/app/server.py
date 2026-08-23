"""MCP Server do estudo de caso (TCC: MCP x APIs Convencionais).

Expõe, via Model Context Protocol (transporte stdio, sessão local), as
mesmas capacidades da implementação REST — consulta a indicadores
macroeconômicos globais — mas seguindo o modelo do MCP: o cliente (o
agente, em client.py) descobre as tools disponíveis dinamicamente e decide
ele mesmo quando e quantas vezes chamá-las dentro de uma única sessão.

Isso contrasta com o REST, onde o backend orquestra explicitamente uma
sequência fixa de 2 chamadas ao LLM (NL->SQL, dados->resposta). Aqui, o
MCP Server só expõe as ferramentas; quem decide o fluxo é o cliente/agente.
"""

from app.db import UnsafeQueryError, init_db, run_safe_select, table_schema_description
from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    name="economic-indicators",
    title="Indicadores Macroeconômicos Globais",
    instructions=(
        "Fornece acesso a uma base de indicadores macroeconômicos globais "
        "(PIB, inflação, desemprego, dívida pública, etc.) por país/ano. "
        "Use 'get_database_schema' primeiro para descobrir a estrutura da "
        "tabela, depois 'query_economic_indicators' com uma query SELECT "
        "para obter os dados necessários para responder à pergunta do usuário."
    ),
)


@mcp.tool()
def get_database_schema() -> str:
    """Retorna o schema SQL da base de indicadores macroeconômicos (tabela
    economic_indicators), para a tool descobrir dinamicamente quais colunas
    e tipos estão disponíveis antes de montar uma query."""
    return table_schema_description()


@mcp.tool()
def query_economic_indicators(sql: str) -> list[dict]:
    """Executa uma query SQL SELECT (somente leitura) contra a tabela
    economic_indicators e retorna as linhas resultantes como uma lista de
    objetos.

    Args:
        sql: Query SQL SELECT válida para SQLite. Apenas SELECT é permitido
            (INSERT/UPDATE/DELETE/DROP/etc. são rejeitados). Use LIMIT para
            evitar retornar muitas linhas de uma vez.
    """
    try:
        return run_safe_select(sql)
    except UnsafeQueryError as e:
        # Devolvemos o erro como resultado (não como exceção não tratada)
        # para que o próprio agente veja a mensagem e possa corrigir a
        # query na próxima chamada da tool, dentro da mesma sessão.
        return [{"error": str(e)}]


def main() -> None:
    init_db()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
