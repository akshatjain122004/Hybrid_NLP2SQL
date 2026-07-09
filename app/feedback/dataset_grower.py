import csv
from pathlib import Path
from sqlalchemy import select, update, func

from app.feedback.miss_tracker import review_queue

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "training" / "intent_dataset.csv"


def grow_dataset(engine, dataset_path: Path = DATASET_PATH) -> int:
    """
    Pulls confirmed-correct, not-yet-grown rows from review_queue and appends
    (nl_query, intent) pairs to intent_dataset.csv. Meant to run nightly (cron/scheduler),
    growing the training set from real confirmed usage instead of only synthetic templates.
    """
    with engine.connect() as conn:
        rows = conn.execute(
            select(review_queue.c.id, review_queue.c.nl_query, review_queue.c.intent)
            .where(review_queue.c.reviewed == True)
            .where(review_queue.c.confirmed_correct == True)
            .where(review_queue.c.grown_at.is_(None))
        ).fetchall()

    if not rows:
        return 0

    with open(dataset_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows([(r.nl_query, r.intent) for r in rows])

    ids = [r.id for r in rows]
    with engine.begin() as conn:
        conn.execute(
            update(review_queue).where(review_queue.c.id.in_(ids))
            .values(grown_at=func.now())
        )

    return len(rows)