from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.etl.metadata import infer_metadata


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}


def parse_txt(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {"source": str(path), "pages": [{"page": 1, "text": text}], "metadata": infer_metadata(path, text)}


def parse_pdf(path: Path) -> dict[str, object]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    pages = []
    preview = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_number, "text": text})
        if len(preview) < 3:
            preview.append(text)
    return {"source": str(path), "pages": pages, "metadata": infer_metadata(path, "\n".join(preview))}


def parse_document(path: Path) -> dict[str, object]:
    if path.suffix.lower() == ".pdf":
        return parse_pdf(path)
    if path.suffix.lower() in {".txt", ".md"}:
        return parse_txt(path)
    raise ValueError(f"Unsupported document type: {path.suffix}")


def parse_directory(input_dir: Path, output_file: Path) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    document_paths = sorted(path for path in input_dir.iterdir() if path.suffix.lower() in SUPPORTED_EXTENSIONS)

    with output_file.open("w", encoding="utf-8") as handle:
        for path in document_paths:
            handle.write(json.dumps(parse_document(path), ensure_ascii=False) + "\n")
    return len(document_paths)


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse raw enterprise documents into JSONL.")
    parser.add_argument("--input", default="data/raw_txts", type=Path)
    parser.add_argument("--output", default="data/cleaned/parsed.jsonl", type=Path)
    args = parser.parse_args()
    count = parse_directory(args.input, args.output)
    print(f"Parsed {count} document(s) into {args.output}")


if __name__ == "__main__":
    main()
