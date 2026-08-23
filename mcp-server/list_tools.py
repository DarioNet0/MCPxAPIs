"""Utilitário simples pra inspecionar as tools expostas pelo MCP Server:
conecta como um cliente de verdade (via stdio) e lista o que o servidor
anuncia via list_tools() — a mesma descoberta dinâmica que o agente
(client.py) usa antes de decidir o que chamar.

Uso:
    python list_tools.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PROJECT_ROOT = str(Path(__file__).parent)


async def main() -> None:
    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.server"], cwd=PROJECT_ROOT, env=dict(os.environ)
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()

            print(f"Servidor: {session.server_info.name if session.server_info else '?'}")
            print(f"{len(result.tools)} tool(s) encontrada(s):\n")

            for tool in result.tools:
                print(f"- {tool.name}")
                print(f"  descrição: {tool.description}")
                print(f"  parâmetros: {json.dumps(tool.input_schema, ensure_ascii=False)}")
                print()


if __name__ == "__main__":
    asyncio.run(main())
