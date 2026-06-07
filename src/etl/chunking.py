from __future__ import annotations

import argparse
import json
from pathlib import Path


def chunk_text(text: str, chunk_size: int = 1_000, overlap: int = 150) -> list[str]:
    if chunk_size <= overlap:
        raise ValueError("chunk_size must be greater than overlap")
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - overlap
    return chunks


def build_chunks(input_file: Path, output_file: Path, chunk_size: int, overlap: int) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with input_file.open("r", encoding="utf-8") as source, output_file.open("w", encoding="utf-8") as target:
        for line in source:
            document = json.loads(line)
            source_name = document["source"]
            for page in document.get("pages", []):
                for index, text in enumerate(chunk_text(page.get("text", ""), chunk_size, overlap)):
                    record = {
                        "id": f"{Path(source_name).stem}-p{page['page']}-c{index}",
                        "source": source_name,
                        "page": page["page"],
                        "chunk_index": index,
                        "text": text,
                    }
                    target.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Split cleaned document pages into chunks.")
    parser.add_argument("--input", default="data/cleaned/cleaned.jsonl", type=Path)
    parser.add_argument("--output", default="data/cleaned/chunks.jsonl", type=Path)
    parser.add_argument("--chunk-size", default=1_000, type=int)
    parser.add_argument("--overlap", default=150, type=int)
    args = parser.parse_args()
    count = build_chunks(args.input, args.output, args.chunk_size, args.overlap)
    print(f"Wrote {count} chunk(s) into {args.output}")


if __name__ == "__main__":
    main()
