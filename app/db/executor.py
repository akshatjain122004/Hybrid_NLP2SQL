from dotenv import load_dotenv
load_dotenv()

import os
import time
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError

DEFAULT_TIMEOUT_SECONDS = 10
_engine = None


def get_engine(database_url: str = None, pool_size: int = 5):
    global _engine
    if _engine is None:
        database_url = database_url or os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL not set -- cannot create DB engine")
        _engine = create_engine(database_url, pool_size=pool_size, pool_pre_ping=True)
    return _engine


def execute_query(sql: str, engine=None, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> dict:
    """Returns: {"success", "columns", "rows", "row_count", "execution_time_ms", "error"}"""
    engine = engine or get_engine()
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            if engine.dialect.name == "postgresql":
                conn.execute(text(f"SET statement_timeout = {timeout_seconds * 1000}"))
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
    except OperationalError as e:
        return {"success": False, "columns": [], "rows": [], "row_count": 0,
                "execution_time_ms": round((time.perf_counter() - start) * 1000, 2),
                "error": f"database connection error: {e}"}
    except SQLAlchemyError as e:
        return {"success": False, "columns": [], "rows": [], "row_count": 0,
                "execution_time_ms": round((time.perf_counter() - start) * 1000, 2),
                "error": str(e)}

    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    return {"success": True, "columns": columns, "rows": rows, "row_count": len(rows),
            "execution_time_ms": elapsed_ms, "error": None}