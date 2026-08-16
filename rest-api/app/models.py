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


class QueryResponse(BaseModel):
    question: str
    sql_generated: str | None
    data: list[dict[str, Any]]
    answer: str
    metrics: QueryMetrics
