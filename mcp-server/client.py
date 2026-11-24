"""Cliente/agente MCP do estudo de caso.

Diferente da implementação REST (onde o backend orquestra explicitamente
2 chamadas fixas ao LLM: NL->SQL e dados->resposta), aqui é o próprio
modelo (Claude) que decide, dentro de uma única sessão com estado, quais
tools chamar e quantas vezes — descobrindo inclusive o schema do banco
dinamicamente via a tool 'get_database_schema' antes de consultar os
dados. O número de round-trips ao LLM não é fixo: pode variar conforme a
complexidade da pergunta (ex.: perguntas de relação entre indicadores
podem exigir mais de uma consulta).

Uso:
    python client.py "Qual foi a média de crescimento do PIB da América do Sul em 2023?"
"""

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from anthropic import Anthropic
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import get_settings

PROJECT_ROOT = str(Path(__file__).parent)
MAX_AGENT_STEPS = 6  # trava de segurança contra loops infinitos de tool use


def _json_bytes(obj) -> int:
    """Tamanho em bytes de um objeto serializado como JSON — mesmo critério
    usado no lado REST (app/llm.py), para as duas implementações ficarem
    comparáveis na métrica de tamanho de mensagem."""
    return len(json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))


def _response_bytes(response) -> int:
    try:
        return _json_bytes(response.model_dump())
    except Exception:
        return len(str(response).encode("utf-8"))


@dataclass
class MCPQueryResult:
    question: str
    answer: str
    tool_calls: list[dict] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {"question": self.question, "answer": self.answer, "tool_calls": self.tool_calls, "metrics": self.metrics},
            ensure_ascii=False,
            indent=2,
            default=str,
        )


def _mcp_tools_to_anthropic_format(mcp_tools) -> list[dict]:
    """Converte as tools descobertas dinamicamente via list_tools() do MCP
    para o formato esperado pela API de tool use da Anthropic."""
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.input_schema,
        }
        for t in mcp_tools
    ]


async def answer_question(question: str) -> MCPQueryResult:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY não configurada. Copie mcp-server/.env.example para "
            "mcp-server/.env e preencha com sua chave (console.anthropic.com/settings/keys)."
        )

    client = Anthropic(api_key=settings.anthropic_api_key)
    # O SDK do MCP, por segurança, NÃO herda automaticamente o ambiente
    # completo do processo pai para o subprocesso do servidor (só uma
    # lista pequena e "segura" de variáveis, tipo PATH). Passamos o
    # DATABASE_PATH explicitamente para garantir que o servidor abra o
    # mesmo banco que o cliente está configurado para usar.
    server_env = {**os.environ, "DATABASE_PATH": settings.database_path}
    server_params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.server"], cwd=PROJECT_ROOT, env=server_env
    )

    total_start = time.perf_counter()
    request_bytes = len(question.encode("utf-8"))
    llm_round_trips = 0
    tool_calls: list[dict] = []
    input_tokens = 0
    output_tokens = 0
    rows_returned = 0
    llm_bytes_sent = 0
    llm_bytes_received = 0
    mcp_bytes_sent = 0
    mcp_bytes_received = 0
    db_payload_bytes = 0

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Descoberta dinâmica de tools — não há schema hardcoded no
            # cliente, diferente do REST onde o schema do banco está
            # embutido no system prompt do backend.
            list_tools_result = await session.list_tools()
            anthropic_tools = _mcp_tools_to_anthropic_format(list_tools_result.tools)

            system_prompt = (
                "Você responde perguntas sobre indicadores macroeconômicos globais. "
                "Use as tools disponíveis: primeiro descubra o schema do banco se "
                "precisar, depois consulte os dados necessários (pode chamar a tool "
                "de consulta mais de uma vez se a pergunta exigir cruzar indicadores "
                "diferentes). Quando tiver os dados suficientes, responda em "
                "português, citando os números relevantes."
            )
            messages = [{"role": "user", "content": question}]

            for _ in range(MAX_AGENT_STEPS):
                request_payload = {
                    "system": system_prompt,
                    "tools": anthropic_tools,
                    "messages": messages,
                }
                llm_bytes_sent += _json_bytes(request_payload)

                llm_start = time.perf_counter()
                response = client.messages.create(
                    model=settings.anthropic_model,
                    max_tokens=1024,
                    **request_payload,
                )
                llm_round_trips += 1
                input_tokens += response.usage.input_tokens
                output_tokens += response.usage.output_tokens
                llm_latency_ms = (time.perf_counter() - llm_start) * 1000
                llm_bytes_received += _response_bytes(response)

                tool_use_blocks = [b for b in response.content if b.type == "tool_use"]

                if not tool_use_blocks:
                    # Resposta final em texto — encerra o loop do agente.
                    final_text = "".join(b.text for b in response.content if b.type == "text")
                    total_latency_ms = (time.perf_counter() - total_start) * 1000
                    # Tamanho do payload de resposta SEM o bloco de metrics
                    # (mesmo critério do REST — evita circularidade).
                    response_bytes = _json_bytes(
                        {"question": question, "answer": final_text, "tool_calls": tool_calls}
                    )
                    return MCPQueryResult(
                        question=question,
                        answer=final_text,
                        tool_calls=tool_calls,
                        metrics={
                            "total_latency_ms": round(total_latency_ms, 2),
                            "llm_round_trips": llm_round_trips,
                            "tool_call_count": len(tool_calls),
                            "last_llm_call_latency_ms": round(llm_latency_ms, 2),
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "rows_returned": rows_returned,
                            "request_bytes": request_bytes,
                            "response_bytes": response_bytes,
                            "llm_bytes_sent": llm_bytes_sent,
                            "llm_bytes_received": llm_bytes_received,
                            "mcp_bytes_sent": mcp_bytes_sent,
                            "mcp_bytes_received": mcp_bytes_received,
                            "db_payload_bytes": db_payload_bytes,
                        },
                    )

                # O modelo pediu pra chamar uma ou mais tools nesta rodada.
                messages.append({"role": "assistant", "content": response.content})
                tool_results_content = []
                for block in tool_use_blocks:
                    tool_request_bytes = _json_bytes({"name": block.name, "input": block.input})

                    call_start = time.perf_counter()
                    result = await session.call_tool(block.name, block.input)
                    call_latency_ms = (time.perf_counter() - call_start) * 1000

                    # A API de tool use da Anthropic espera um texto único
                    # como resultado da tool. O SDK do MCP quebra listas em
                    # múltiplos blocos de texto (um por item) em 'content',
                    # o que não é confiável pra reconstruir a lista original
                    # (e vira um único dict "solto" quando há 1 item só).
                    # 'structured_content' preserva o formato original
                    # ({"result": [...]}), então usamos ele como fonte da
                    # verdade e serializamos nós mesmos de volta pro LLM.
                    if result.structured_content and "result" in result.structured_content:
                        payload = result.structured_content["result"]
                    else:
                        payload = "".join(c.text for c in result.content if c.type == "text")
                    result_text = json.dumps(payload, ensure_ascii=False, default=str)

                    mcp_bytes_sent += tool_request_bytes
                    mcp_bytes_received += len(result_text.encode("utf-8"))

                    tool_calls.append(
                        {
                            "tool": block.name,
                            "input": block.input,
                            "latency_ms": round(call_latency_ms, 2),
                            "is_error": result.is_error,
                        }
                    )
                    if block.name == "query_economic_indicators" and not result.is_error and isinstance(payload, list):
                        rows_returned += len(payload)
                        db_payload_bytes += len(result_text.encode("utf-8"))

                    tool_results_content.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                            "is_error": result.is_error,
                        }
                    )
                messages.append({"role": "user", "content": tool_results_content})

            raise RuntimeError(f"Agente excedeu o limite de {MAX_AGENT_STEPS} passos sem chegar a uma resposta final.")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Uso: python client.py "sua pergunta aqui"')
    result = asyncio.run(answer_question(sys.argv[1]))
    print(result.to_json())


if __name__ == "__main__":
    main()
