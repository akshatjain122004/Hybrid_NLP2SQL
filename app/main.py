import asyncio
import logging
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
from app.cache.semantic_cache import check_cache, add_to_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("nl2sql")

_router = None
_qdrant_client = None
_db_engine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _router, _qdrant_client, _db_engine
    overall_start = time.perf_counter()

    t = time.perf_counter()
    _router = build_router()
    logger.info(f"[startup] router built in {(time.perf_counter()-t)*1000:.0f}ms")

    t = time.perf_counter()
    _qdrant_client = get_qdrant_client()
    try:
        count = warm_cache(client=_qdrant_client)
        logger.info(f"[startup] cache ready ({count} points) in {(time.perf_counter()-t)*1000:.0f}ms")
    except Exception as e:
        logger.warning(f"[startup] cache warm failed (non-fatal): {e}")

    t = time.perf_counter()
    _db_engine = get_engine()
    ensure_log_table(_db_engine)
    ensure_review_table(_db_engine)
    logger.info(f"[startup] DB engine + tables ready in {(time.perf_counter()-t)*1000:.0f}ms")

    logger.info(f"[startup] TOTAL startup time: {(time.perf_counter()-overall_start)*1000:.0f}ms")
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
    tokens: Optional[dict] = None  # {"prompt_tokens", "completion_tokens", "total_tokens"} -- only set when source == "llm_fallback"/"unsupported"
    error: Optional[str] = None


def _run_pipeline_sync(raw_query: str) -> dict:
    t0 = time.perf_counter()
    cache_result = check_cache(raw_query, client=_qdrant_client)
    logger.info(f"[cache_check] {(time.perf_counter()-t0)*1000:.1f}ms hit={cache_result['hit']} score={cache_result['score']:.3f}")

    intent_for_review, tokens = "cached", None
    if cache_result["hit"]:
        sql, source, confidence = cache_result["sql"], "cache", cache_result["score"]
    else:
        t = time.perf_counter()
        state = _router.invoke({"raw_query": raw_query})
        logger.info(f"[router] {(time.perf_counter()-t)*1000:.1f}ms source={state['source']}")
        if state["source"] in ("rejected", "unsupported"):
            return {"early_exit": True, "state": state}
        sql, source, confidence = state["sql"], state["source"], state.get("confidence")
        intent_for_review = state.get("intent", "unknown")
        tokens = state.get("tokens")  # only populated when this went through the LLM fallback

    t = time.perf_counter()
    syntax, safety, whitelist = validate_syntax(sql), check_safety(sql), check_whitelist(sql)
    logger.info(f"[validation] {(time.perf_counter()-t)*1000:.1f}ms syntax={syntax['valid']} safety={safety['safe']} whitelist={whitelist['allowed']}")

    if not (syntax["valid"] and safety["safe"] and whitelist["allowed"]):
        error_msg = (syntax["error"] or safety["reason"]
                     or f"blocked tables/columns: {whitelist['bad_tables']}{whitelist['bad_columns']}")
        return {"early_exit": False, "validation_failed": True, "sql": sql, "source": source,
                "confidence": confidence, "error": error_msg, "tokens": tokens}

    t = time.perf_counter()
    execution = execute_query(sql, engine=_db_engine)
    logger.info(f"[execute] {(time.perf_counter()-t)*1000:.1f}ms rows={execution['row_count']} success={execution['success']}")

    return {"early_exit": False, "validation_failed": False, "sql": sql, "source": source,
            "confidence": confidence, "execution": execution, "intent_for_review": intent_for_review,
            "tokens": tokens}


@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest):
    start = time.perf_counter()
    raw_query = request.query.strip()
    if not raw_query:
        raise HTTPException(status_code=400, detail="query cannot be empty")

    logger.info(f"Received query: {raw_query!r}")
    result = await asyncio.to_thread(_run_pipeline_sync, raw_query)

    if result.get("early_exit"):
        state = result["state"]
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        await log_query(_db_engine, nl_query=raw_query, sql_query=None, source=state["source"],
                         success=False, execution_time_ms=elapsed, error=state["error"])
        logger.info(f"Query rejected/unsupported in {elapsed}ms: {state['error']}")
        return QueryResponse(success=False, nl_query=raw_query, sql=None, source=state["source"],
                              execution_time_ms=elapsed, error=state["error"], tokens=state.get("tokens"))

    if result["validation_failed"]:
        elapsed = round((time.perf_counter() - start) * 1000, 2)
        await log_query(_db_engine, nl_query=raw_query, sql_query=result["sql"], source=result["source"],
                         success=False, execution_time_ms=elapsed, confidence=result["confidence"], error=result["error"])
        logger.warning(f"Validation failed in {elapsed}ms: {result['error']}")
        return QueryResponse(success=False, nl_query=raw_query, sql=result["sql"], source=result["source"],
                              execution_time_ms=elapsed, confidence=result["confidence"], error=result["error"],
                              tokens=result.get("tokens"))

    execution = result["execution"]
    formatted = format_result(execution, source=result["source"], nl_query=raw_query)
    formatted["confidence"], formatted["sql"], formatted["tokens"] = result["confidence"], result["sql"], result.get("tokens")

    await log_query(_db_engine, nl_query=raw_query, sql_query=result["sql"], source=result["source"],
                     success=execution["success"], row_count=execution["row_count"],
                     execution_time_ms=execution["execution_time_ms"], confidence=result["confidence"],
                     error=execution["error"])

    if result["source"] == "llm_fallback":
        flag_for_review(_db_engine, nl_query=raw_query, sql_query=result["sql"],
                         intent=result["intent_for_review"], confidence=result["confidence"] or 0.0)
        if execution["success"]:
            add_to_cache(raw_query, result["sql"], client=_qdrant_client)

    total_elapsed = round((time.perf_counter() - start) * 1000, 2)
    logger.info(f"Query complete in {total_elapsed}ms source={result['source']} rows={execution['row_count']} tokens={result.get('tokens')}")

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