from sqlalchemy import (MetaData, Table, Column, Integer, String, Text, Float,
                         Boolean, DateTime, func, select, update)

metadata = MetaData()

review_queue = Table(
    "review_queue", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("nl_query", Text, nullable=False),
    Column("sql_query", Text),
    Column("intent", String(30)),
    Column("confidence", Float),
    Column("reviewed", Boolean, default=False),
    Column("confirmed_correct", Boolean),
    Column("grown_at", DateTime),
    Column("created_at", DateTime, server_default=func.now()),
)


def ensure_review_table(engine):
    metadata.create_all(engine, tables=[review_queue])


def flag_for_review(engine, nl_query: str, sql_query: str, intent: str, confidence: float):
    """Called whenever source == 'llm_fallback' -- every LLM-generated query needs a human check."""
    with engine.begin() as conn:
        conn.execute(review_queue.insert().values(
            nl_query=nl_query, sql_query=sql_query, intent=intent,
            confidence=confidence, reviewed=False,
        ))


def get_pending_reviews(engine, limit: int = 50) -> list:
    with engine.connect() as conn:
        result = conn.execute(
            select(review_queue).where(review_queue.c.reviewed == False)
            .order_by(review_queue.c.created_at).limit(limit)
        )
        return [dict(row._mapping) for row in result]


def mark_reviewed(engine, review_id: int, confirmed_correct: bool):
    with engine.begin() as conn:
        conn.execute(
            update(review_queue).where(review_queue.c.id == review_id)
            .values(reviewed=True, confirmed_correct=confirmed_correct)
        )