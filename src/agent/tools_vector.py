from __future__ import annotations

import os

from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class VectorSearchTool:
    def __init__(
        self,
        qdrant_url: str | None = None,
        collection: str | None = None,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        self.collection = collection or os.getenv("QDRANT_COLLECTION", "finance_docs")
        self.client = QdrantClient(url=qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333"))
        self.model = SentenceTransformer(model_name)

    def search(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        vector = self.model.encode(query).tolist()
        results = self.client.search(collection_name=self.collection, query_vector=vector, limit=limit)
        return [
            {
                "score": result.score,
                "source": result.payload.get("source"),
                "page": result.payload.get("page"),
                "text": result.payload.get("text"),
            }
            for result in results
        ]
