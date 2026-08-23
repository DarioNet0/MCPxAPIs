import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.config import get_settings

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

# Mesma barreira de segurança da implementação REST: o LLM só pode mandar
# SELECT. Aqui a diferença é que quem invoca esta função é uma *tool* do
# MCP, chamada pelo próprio modelo dentro do loop do agente — não um
# handler HTTP escrito por nós. A validação é o que impede que uma tool
# aparentemente inofensiva vire uma porta para SQL injection/DROP via LLM.
_ALLOWED_STATEMENT = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|PRAGMA|CREATE|REPLACE)\b", re.IGNORECASE
)


class UnsafeQueryError(ValueError):
    pass


def init_db() -> None:
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
    return SCHEMA_PATH.read_text(encoding="utf-8")
