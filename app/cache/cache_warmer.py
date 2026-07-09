import os
import json
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_cache" / "nl_sql_pairs.json"
COLLECTION_NAME = "nl_sql_cache"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

def get_qdrant_client(location: str = "server", host: str = None, port: int = 6333) -> QdrantClient:
    host = host or os.environ.get("QDRANT_HOST", "localhost")
    if location == ":memory:":
        return QdrantClient(location=":memory:")
    if location == "server":
        return QdrantClient(host=host, port=port)
    return QdrantClient(path=location)


def warm_cache(client: QdrantClient = None, seed_path: Path = SEED_PATH) -> int:
    client = client or get_qdrant_client()
    model = SentenceTransformer(EMBEDDING_MODEL)

    with open(seed_path, "r", encoding="utf-8") as f:
        pairs = json.load(f)

    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=model.get_embedding_dimension(), distance=Distance.COSINE
            ),
        )

    embeddings = model.encode([p["nl"] for p in pairs])
    points = [
        PointStruct(id=i, vector=embeddings[i].tolist(), payload=pairs[i])
        for i in range(len(pairs))
    ]
    client.upsert(collection_name=COLLECTION_NAME, points=points)
    return len(points)


if __name__ == "__main__":
    print(f"Warmed cache with {warm_cache()} seed pairs.")