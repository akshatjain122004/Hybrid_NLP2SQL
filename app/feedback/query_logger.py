import asyncio
import functools
from sqlalchemy import MetaData, Table, Column, Integer, String, Text, Float, Boolean, DateTime, func

metadata = MetaData()

query_logs = Table(
    "query_logs", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nl_query", Text, nullable=False),
    Column("sql_query", Text),
    Column("source", String(20)),
    Column("success", Boolean),
    Column("row_count", Integer),
    Column("execution_time_ms", Float),
    Column("confidence", Float),
    Column("error", Text),
    Column("created_at", DateTime, server_default=func.now()),
)


def ensure_log_table(engine):
    metadata.create_all(engine, tables=[query_logs])


def _insert_log_sync(engine, **kwargs):
    with engine.begin() as conn:
        conn.execute(query_logs.insert().values(**kwargs))


async def log_query(engine, nl_query: str, sql_query: str, source: str, success: bool,
                     row_count: int = 0, execution_time_ms: float = 0.0,
                     confidence: float = None, error: str = None):
    """
    Async wrapper around a sync SQLAlchemy insert -- keeps the caller (FastAPI endpoint,
    Phase 10) non-blocking without needing a full asyncpg/async-engine rebuild yet.
    """
    loop = asyncio.get_event_loop()
    fn = functools.partial(
        _insert_log_sync, engine,
        nl_query=nl_query, sql_query=sql_query, source=source, success=success,
        row_count=row_count, execution_time_ms=execution_time_ms,
        confidence=confidence, error=error,
    )
    await loop.run_in_executor(None, fn)