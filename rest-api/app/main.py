import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app import llm
from app.db import UnsafeQueryError, init_db, run_safe_select
from app.models import QueryMetrics, QueryRequest, QueryResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rest_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("Banco de dados inicializado.")
    yield


app = FastAPI(
    title="TCC — REST API (MCP x APIs Convencionais)",
    description=(
        "Endpoint REST do estudo de caso: consulta a indicadores macroeconômicos "
        "globais + geração de resposta contextualizada via LLM (Claude Haiku)."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    """Endpoint principal do experimento.

    Fluxo (stateless, cada chamada independente — característica central
    da comparação REST x MCP no TCC):
      1. LLM traduz a pergunta em SQL (round-trip 1)
      2. Backend executa o SQL no SQLite (com validação de segurança)
      3. LLM gera a resposta contextualizada a partir dos dados (round-trip 2)
    """
    total_start = time.perf_counter()

    try:
        sql_result = llm.generate_sql(request.question)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    try:
        rows = run_safe_select(sql_result.sql)
    except UnsafeQueryError as e:
        raise HTTPException(status_code=422, detail=f"Query gerada rejeitada por segurança: {e}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao executar SQL gerado pelo LLM: {e}") from e
    sql_exec_end = time.perf_counter()

    try:
        answer_result = llm.generate_answer(request.question, rows)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    total_latency_ms = (time.perf_counter() - total_start) * 1000
    sql_execution_latency_ms = (sql_exec_end - total_start) * 1000 - sql_result.latency_ms

    metrics = QueryMetrics(
        total_latency_ms=round(total_latency_ms, 2),
        llm_round_trips=2,
        sql_generation_latency_ms=round(sql_result.latency_ms, 2),
        sql_execution_latency_ms=round(max(sql_execution_latency_ms, 0), 2),
        answer_generation_latency_ms=round(answer_result.latency_ms, 2),
        input_tokens=sql_result.input_tokens + answer_result.input_tokens,
        output_tokens=sql_result.output_tokens + answer_result.output_tokens,
        rows_returned=len(rows),
    )

    logger.info("query=%r sql=%r metrics=%s", request.question, sql_result.sql, metrics.model_dump())

    return QueryResponse(
        question=request.question,
        sql_generated=sql_result.sql,
        data=rows,
        answer=answer_result.text,
        metrics=metrics,
    )
