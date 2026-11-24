import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Só permitimos SELECT vindo do LLM (a consulta é gerada dinamicamente
# a partir da pergunta do usuário, então isso é uma proteção obrigatória
# contra prompt injection / SQL injection via LLM).
_ALLOWED_STATEMENT = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|PRAGMA|CREATE|REPLACE)\b", re.IGNORECASE
)


class UnsafeQueryError(ValueError):
    pass


def init_db() -> None:
    """Cria o schema (idempotente) caso o banco ainda não exista/esteja vazio."""
    settings = get_settings()
    settings.database_abs_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


@contextmanager
def get_connection():
    settings = get_settings()
    conn = sqlite3.connect(settings.database_abs_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def run_safe_select(sql: str, params: tuple = ()) -> list[dict]:
    """Executa uma query SELECT somente-leitura e retorna as linhas como dicts.

    Lança UnsafeQueryError se a query não for um SELECT limpo — essa é a
    barreira de segurança entre o SQL gerado pelo LLM e o banco real.
    """
    if not _ALLOWED_STATEMENT.match(sql):
        raise UnsafeQueryError("Apenas instruções SELECT são permitidas.")
    if _FORBIDDEN_KEYWORDS.search(sql):
        raise UnsafeQueryError("Query contém palavra-chave não permitida.")
    if ";" in sql.strip().rstrip(";"):
        raise UnsafeQueryError("Múltiplas instruções não são permitidas.")

    with get_connection() as conn:
        cursor = conn.execute(sql, params)
        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(columns, row)) for row in rows]


def table_schema_description() -> str:
    """Retorna a descrição textual do schema para dar de contexto ao LLM."""
    return SCHEMA_PATH.read_text(encoding="utf-8")
