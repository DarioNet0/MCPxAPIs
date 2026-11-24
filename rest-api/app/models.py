from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Pergunta em linguagem natural sobre indicadores econômicos.")
    category: Literal["isolated", "cross", "unknown"] | None = Field(
        default=None, description="Categoria da pergunta para fins de coleta de métricas do experimento."
    )


class QueryMetrics(BaseModel):
    total_latency_ms: float
    llm_round_trips: int
    sql_generation_latency_ms: float
    sql_execution_latency_ms: float
    answer_generation_latency_ms: float
    input_tokens: int
    output_tokens: int
    rows_returned: int
    # --- Métricas de tamanho de payload (bytes), adicionadas em 10/09/2026
    # para fechar a métrica "tamanho das mensagens trocadas" planejada no
    # desenho experimental do TCC ---
    request_bytes: int = 0
    """Tamanho (bytes) do corpo da requisição HTTP recebida em /query."""
    response_bytes: int = 0
    """Tamanho (bytes) do corpo da resposta, SEM contar o próprio bloco de
    metrics (evita circularidade: o tamanho da resposta não pode depender
    do campo que guarda o tamanho da resposta)."""
    llm_bytes_sent: int = 0
    """Soma dos bytes enviados à Anthropic API nas 2 chamadas (system +
    tools + messages), serializados como JSON."""
    llm_bytes_received: int = 0
    """Soma dos bytes recebidos da Anthropic API nas 2 chamadas."""
    db_payload_bytes: int = 0
    """Tamanho (bytes) dos dados retornados pela consulta SQL (JSON), antes
    de virar contexto para o round-trip de geração de resposta."""


class QueryResponse(BaseModel):
    question: str
    sql_generated: str | None
    data: list[dict[str, Any]]
    answer: str
    metrics: QueryMetrics
