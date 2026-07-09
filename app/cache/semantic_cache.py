from sentence_transformers import SentenceTransformer

from app.cache.cache_warmer import get_qdrant_client, COLLECTION_NAME, EMBEDDING_MODEL

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def check_cache(query: str, client=None, threshold: float = 0.92) -> dict:
    """Returns {"hit": bool, "score": float, "sql": str|None, "matched_query": str|None}"""
    client = client or get_qdrant_client()
    vector = _get_model().encode(query).tolist()

    response = client.query_points(collection_name=COLLECTION_NAME, query=vector, limit=1)
    results = response.points
    if not results:
        return {"hit": False, "score": 0.0, "sql": None, "matched_query": None}

    top = results[0]
    if top.score >= threshold:
        return {"hit": True, "score": top.score, "sql": top.payload["sql"], "matched_query": top.payload["nl"]}
    return {"hit": False, "score": top.score, "sql": None, "matched_query": None}