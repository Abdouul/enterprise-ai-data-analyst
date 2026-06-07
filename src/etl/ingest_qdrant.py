from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def ingest_chunks(input_file: Path, collection: str, qdrant_url: str, model_name: str = DEFAULT_MODEL) -> int:
    model = SentenceTransformer(model_name)
    client = QdrantClient(url=qdrant_url)
    vector_size = model.get_sentence_embedding_dimension()

    client.recreate_collection(
        collection_name=collection,
        vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
    )

    points = []
    with input_file.open("r", encoding="utf-8") as handle:
        for offset, line in enumerate(handle):
            record = json.loads(line)
            vector = model.encode(record["text"]).tolist()
            points.append(PointStruct(id=offset, vector=vector, payload=record))

    if points:
        client.upsert(collection_name=collection, points=points)
    return len(points)


def main() -> None:
    parser = argparse.ArgumentParser(description="Embed chunks and ingest them into Qdrant.")
    parser.add_argument("--input", default="data/cleaned/chunks.jsonl", type=Path)
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "finance_docs"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    count = ingest_chunks(args.input, args.collection, args.qdrant_url, args.model)
    print(f"Ingested {count} chunk(s) into Qdrant collection {args.collection}")


if __name__ == "__main__":
    main()
