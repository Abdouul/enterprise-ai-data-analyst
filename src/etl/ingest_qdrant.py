from __future__ import annotations

import argparse
import json
import os
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def point_id(chunk_id: str) -> str:
    """Create a deterministic UUID for a chunk ID.

    Deterministic IDs make repeated ingestion predictable: the same chunk gets
    the same Qdrant point ID each time the pipeline runs.
    """
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


def ingest_chunks(
    input_file: Path,
    collection: str,
    qdrant_url: str,
    model_name: str = DEFAULT_MODEL,
    batch_size: int = 64,
    qdrant_api_key: str | None = None,
) -> int:
    """Embed cleaned chunks with a local HuggingFace model and upsert to Qdrant."""
    model = SentenceTransformer(model_name)
    api_key = (qdrant_api_key or os.getenv("QDRANT_API_KEY") or "").strip() or None
    client = QdrantClient(url=qdrant_url, api_key=api_key)
    vector_size = model.get_sentence_embedding_dimension()

    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    points: list[PointStruct] = []
    total = 0
    with input_file.open("r", encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            vector = model.encode(record["text"]).tolist()
            payload = {**record, "metadata": record.get("metadata", {})}
            points.append(PointStruct(id=point_id(record["id"]), vector=vector, payload=payload))
            if len(points) >= batch_size:
                client.upsert(collection_name=collection, points=points)
                total += len(points)
                points = []

    if points:
        client.upsert(collection_name=collection, points=points)
        total += len(points)
    return total


def main() -> None:
    """Expose vector ingestion as a command-line script."""
    parser = argparse.ArgumentParser(description="Embed chunks and ingest them into Qdrant.")
    parser.add_argument("--input", default="data/cleaned/chunks.jsonl", type=Path)
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "finance_docs"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", default=64, type=int)
    args = parser.parse_args()
    count = ingest_chunks(args.input, args.collection, args.qdrant_url, args.model, args.batch_size, args.qdrant_api_key)
    print(f"Ingested {count} chunk(s) into Qdrant collection {args.collection}")


if __name__ == "__main__":
    main()
