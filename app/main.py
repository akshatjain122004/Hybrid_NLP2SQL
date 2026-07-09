import time
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from app.router.langgraph_router import build_router
from app.validator.syntax_validator import validate_syntax
from app.validator.safety_guard import check_safety
from app.validator.whitelist import check_whitelist
from app.db.executor import get_engine, execute_query
from app.db.result_formatter import format_result
from app.feedback.query_logger import ensure_log_table, log_query, query_logs
from app.feedback.miss_tracker import ensure_review_table, flag_for_review
from app.cache.cache_warmer import warm_cache, get_qdrant_client
from app.cache.semantic_cache import check_cache

_router = None
_qdrant_client = None
_db_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _router, _qdrant_client, _db_engine
    _router = build_router()
    _qdrant_client = get_qdrant_client()
    try:
        warm_cache(client=_qdrant_client)
    except Exception as e:
        print(f"Cache warm failed (non-fatal, continuing without warm cache): {e}")
    _db_engine = get_engine()
    ensure_log_table(_db_engine)
    ensure_review_table(_db_engine)
    yield


app = FastAPI(title="Hybrid NL2SQL API", lifespan=lifespan)


class QueryRequest(BaseModel):
    query: str


class QueryResponse(BaseModel):
    success: bool
    nl_query: str
    sql: Optional[str] = None
    source: str
    columns: list = []
    rows: list = []
    row_count: int = 0
    execution_time_ms: float = 0.0
    confidence: Optional[float] = None
    error: Optional[str] = None


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    start = time.perf_counter()
    raw_query = request.query.strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    cache_result = check_cache(raw_query, client=_qdrant_client)
    intent_for_review = "cached"
    if cache_result["hit"]:
        sql, source, confidence = cache_result["sql"], "cache", cache_result["score"]
    else:
        state = _router.invoke({"raw_query": raw_query})
        if state["source"] == "rejected":
            elapsed = round((time.perf_counter() - start) * 1000, 2)
            await log_query(_db_engine, nl_query=raw_query, sql_query=None, source="rejected",
                             success=False, execution_time_ms=elapsed, error=state["error"])
            return QueryResponse(success=False, nl_query=raw_query, sql=None, source="rejected",
                                  execution_time_ms=elapsed, error=state["error"])
        sql, source, confidence = state["sql"], state["source"], state.get("confidence")
        intent_for_review = state.get("intent", "unknown")

    syntax, safety, whitelist = validate_syntax(sql), check_safety(sql), check_whitelist(sql)
    if not (syntax["valid"] and safety["safe"] and whitelist["allowed"]):
        error_msg = (syntax["error"] or safety["reason"]
                     or f"blocked tables/columns: {whitelist['bad_tables']}{whitelist['bad_columns']}")
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        await log_query(_db_engine, nl_query=raw_query, sql_query=sql, source=source,
                         success=False, execution_time_ms=elapsed, confidence=confidence, error=error_msg)
        return QueryResponse(success=False, nl_query=raw_query, sql=sql, source=source,
                              execution_time_ms=elapsed, confidence=confidence, error=error_msg)

    execution = execute_query(sql, engine=_db_engine)
    formatted = format_result(execution, source=source, nl_query=raw_query)
    formatted["confidence"], formatted["sql"] = confidence, sql

    await log_query(_db_engine, nl_query=raw_query, sql_query=sql, source=source,
                     success=execution["success"], row_count=execution["row_count"],
                     execution_time_ms=execution["execution_time_ms"], confidence=confidence,
                     error=execution["error"])
    if source == "llm_fallback":
        flag_for_review(_db_engine, nl_query=raw_query, sql_query=sql,
                         intent=intent_for_review, confidence=confidence or 0.0)

    return QueryResponse(**formatted)


@app.get("/metrics")
async def metrics():
    with _db_engine.connect() as conn:
        total = conn.execute(select(func.count()).select_from(query_logs)).scalar() or 0
        if total == 0:
            return {"total_queries": 0, "cache_hit_rate": None, "llm_bypass_rate": None, "avg_latency_ms": None}

        cache_hits = conn.execute(
            select(func.count()).select_from(query_logs).where(query_logs.c.source == "cache")
        ).scalar() or 0
        llm_calls = conn.execute(
            select(func.count()).select_from(query_logs).where(query_logs.c.source == "llm_fallback")
        ).scalar() or 0
        avg_latency = conn.execute(select(func.avg(query_logs.c.execution_time_ms))).scalar()

    return {
        "total_queries": total,
        "cache_hit_rate": round(cache_hits / total, 4),
        "llm_bypass_rate": round(1 - (llm_calls / total), 4),
        "avg_latency_ms": round(avg_latency, 2) if avg_latency else None,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}