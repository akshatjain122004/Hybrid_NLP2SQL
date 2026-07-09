import re


def dry_run(sql: str, engine=None, max_estimated_rows: int = 100_000) -> dict:
    """
    engine: SQLAlchemy Engine. None (default) -> skipped, since app/db/executor.py
    (Phase 9) doesn't exist yet -- there's no live DB connection to EXPLAIN against.
    This function is correct and ready; it just has nothing to connect to until
    Phase 9 builds executor.py.
    """
    if engine is None:
        return {"ok": None, "estimated_rows": None, "error": None,
                "note": "no DB engine configured -- dry run skipped, Phase 9 dependency"}

    from sqlalchemy import text
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"EXPLAIN {sql}"))
            plan_lines = [row[0] for row in result]
    except Exception as e:
        return {"ok": False, "estimated_rows": None, "error": str(e), "note": None}

    plan_text = "\n".join(plan_lines)
    match = re.search(r"rows=(\d+)", plan_text)
    estimated_rows = int(match.group(1)) if match else None

    if estimated_rows is not None and estimated_rows > max_estimated_rows:
        return {"ok": False, "estimated_rows": estimated_rows, "note": None,
                "error": f"estimated {estimated_rows} rows exceeds limit of {max_estimated_rows}"}

    return {"ok": True, "estimated_rows": estimated_rows, "error": None, "note": None}