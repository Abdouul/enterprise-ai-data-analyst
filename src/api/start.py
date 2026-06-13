from __future__ import annotations

import os
from pathlib import Path

import uvicorn

from src.etl.create_finance_db import create_finance_db


def initialize_local_vector_db() -> None:
    """Build the embedded Qdrant collection used by a standalone Cloud Run instance."""
    qdrant_path = os.getenv("QDRANT_PATH")
    if not qdrant_path:
        return

    from src.etl.ingest_qdrant import ingest_chunks

    chunks_path = Path(os.getenv("CHUNKS_PATH", "data/cleaned/chunks.jsonl"))
    collection = os.getenv("QDRANT_COLLECTION", "finance_docs")
    count = ingest_chunks(
        chunks_path,
        collection,
        qdrant_url=None,
        qdrant_path=qdrant_path,
    )
    print(f"[startup] qdrant_path={qdrant_path} collection={collection} vectors={count}")


def main() -> None:
    """Create the local SQLite dataset and start FastAPI on Cloud Run's port."""
    db_path = Path(os.getenv("FINANCE_DB_PATH", "data/finance.db"))
    row_count = create_finance_db(db_path)
    print(f"[startup] finance_db={db_path} rows={row_count}")
    initialize_local_vector_db()

    uvicorn.run(
        "src.api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
