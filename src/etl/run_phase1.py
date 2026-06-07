from __future__ import annotations

import argparse
import os
from pathlib import Path

from src.etl.chunking import build_chunks
from src.etl.clean_text import clean_jsonl
from src.etl.parse_documents import parse_directory


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def run_pipeline(
    input_dir: Path,
    output_dir: Path,
    ingest: bool,
    qdrant_url: str,
    collection: str,
    model: str,
) -> dict[str, object]:
    parsed_path = output_dir / "parsed.jsonl"
    cleaned_path = output_dir / "cleaned.jsonl"
    chunks_path = output_dir / "chunks.jsonl"

    parsed_count = parse_directory(input_dir, parsed_path)
    cleaned_count = clean_jsonl(parsed_path, cleaned_path)
    chunk_count = build_chunks(cleaned_path, chunks_path, max_words=220, overlap_sentences=1)
    ingested_count = 0
    if ingest:
        from src.etl.ingest_qdrant import ingest_chunks

        ingested_count = ingest_chunks(chunks_path, collection, qdrant_url, model)

    return {
        "parsed_documents": parsed_count,
        "cleaned_documents": cleaned_count,
        "chunks": chunk_count,
        "ingested_vectors": ingested_count,
        "chunks_path": str(chunks_path),
        "collection": collection,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 1 Vector ETL pipeline end to end.")
    parser.add_argument("--input", default="data/raw_txts", type=Path)
    parser.add_argument("--output", default="data/cleaned", type=Path)
    parser.add_argument("--ingest", action="store_true", help="Insert embedded chunks into Qdrant.")
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--collection", default=os.getenv("QDRANT_COLLECTION", "finance_docs"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    result = run_pipeline(args.input, args.output, args.ingest, args.qdrant_url, args.collection, args.model)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
