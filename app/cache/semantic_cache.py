from sentence_transformers import SentenceTransformer

from app.cache.cache_warmer import get_qdrant_client, COLLECTION_NAME, EMBEDDING_MODEL
import re
import uuid
from qdrant_client.models import PointStruct

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _extract_numbers(text: str) -> set:
    return set(re.findall(r"\d+", text))


def check_cache(query: str, client=None, threshold: float = 0.92) -> dict:
    """Returns {"hit": bool, "score": float, "sql": str|None, "matched_query": str|None}"""
    client = client or get_qdrant_client()
    vector = _get_model().encode(query).tolist()

    response = client.query_points(
        collection_name=COLLECTION_NAME, query=vector, limit=1
    )
    results = response.points
    if not results:
        return {"hit": False, "score": 0.0, "sql": None, "matched_query": None}

    top = results[0]
    if top.score < threshold:
        return {"hit": False, "score": top.score, "sql": None, "matched_query": None}

    # Embeddings weight numeric literals weakly -- "40%" vs "10%" can score as
    # near-identical even though they change the query's meaning entirely.
    # Explicit guard: if the numbers present in the two queries differ, it's not
    # a real match regardless of how high the embedding similarity scored.
    if _extract_numbers(query) != _extract_numbers(top.payload["nl"]):
        return {"hit": False, "score": top.score, "sql": None, "matched_query": None}

    return {
        "hit": True,
        "score": top.score,
        "sql": top.payload["sql"],
        "matched_query": top.payload["nl"],
    }


def add_to_cache(nl_query: str, sql: str, client=None):
    """
    Writes a new (query, sql) pair into the semantic cache -- called after a
    successful LLM fallback, so the next time someone asks something close to
    this, it hits the cache instead of calling the LLM again.

    Uses a UUID instead of an incrementing int ID, since cache_warmer.py's seed
    pairs already occupy IDs 0..N-1 -- a UUID guarantees no collision with those
    or with other dynamically-added entries, without needing to track a counter.
    """
    client = client or get_qdrant_client()
    vector = _get_model().encode(nl_query).tolist()
    point = PointStruct(
        id=str(uuid.uuid4()), vector=vector, payload={"nl": nl_query, "sql": sql}
    )
    client.upsert(collection_name=COLLECTION_NAME, points=[point])
