from __future__ import annotations

import argparse
import json
from pathlib import Path

from pypdf import PdfReader


def parse_pdf(path: Path) -> dict[str, str]:
    """Extract text page by page from a PDF file.

    This module is kept as a small PDF-only utility. The main Phase 1 parser is
    `parse_documents.py`, which supports both PDF and text files.
    """
    reader = PdfReader(str(path))
    pages = []
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append({"page": page_number, "text": text})
    return {"source": str(path), "pages": pages}


def parse_directory(input_dir: Path, output_file: Path) -> int:
    """Parse all PDFs in a directory and write one document per JSONL line."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with output_file.open("w", encoding="utf-8") as handle:
        for pdf_path in sorted(input_dir.glob("*.pdf")):
            handle.write(json.dumps(parse_pdf(pdf_path), ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    """Expose PDF-only parsing as a command-line script."""
    parser = argparse.ArgumentParser(description="Extract text from PDF files into JSONL.")
    parser.add_argument("--input", default="data/raw_pdfs", type=Path)
    parser.add_argument("--output", default="data/cleaned/parsed.jsonl", type=Path)
    args = parser.parse_args()
    count = parse_directory(args.input, args.output)
    print(f"Parsed {count} PDF file(s) into {args.output}")


if __name__ == "__main__":
    main()
