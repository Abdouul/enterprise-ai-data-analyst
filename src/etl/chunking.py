from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


HEADING_RE = re.compile(r"^[A-Z0-9][A-Z0-9 &().,/'':\-–—]{6,}$")


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def sectionize(text: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_title = "Document Overview"
    current_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or set(line) <= {"="}:
            current_lines.append("")
            continue
        is_heading = bool(HEADING_RE.match(line)) and word_count(line) <= 12
        if is_heading and current_lines:
            body = "\n".join(current_lines).strip()
            if body:
                sections.append({"title": current_title, "text": body})
            current_title = line.title()
            current_lines = []
        elif is_heading:
            current_title = line.title()
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        sections.append({"title": current_title, "text": body})
    return sections


def chunk_section(section_text: str, max_words: int = 220, overlap_sentences: int = 1) -> list[str]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", section_text) if paragraph.strip()]
    chunks = []
    current: list[str] = []
    current_words = 0

    for paragraph in paragraphs:
        paragraph_words = word_count(paragraph)
        if current and current_words + paragraph_words > max_words:
            chunks.append("\n\n".join(current).strip())
            overlap = current[-overlap_sentences:] if overlap_sentences > 0 else []
            current = overlap + [paragraph]
            current_words = sum(word_count(item) for item in current)
        else:
            current.append(paragraph)
            current_words += paragraph_words

    if current:
        chunks.append("\n\n".join(current).strip())
    return chunks


def build_chunks(input_file: Path, output_file: Path, max_words: int, overlap_sentences: int) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with input_file.open("r", encoding="utf-8") as source, output_file.open("w", encoding="utf-8") as target:
        for line in source:
            document = json.loads(line)
            source_name = document["source"]
            metadata = document.get("metadata", {})
            for page in document.get("pages", []):
                for section in sectionize(page.get("text", "")):
                    for index, text in enumerate(chunk_section(section["text"], max_words, overlap_sentences)):
                        chunk_metadata = {
                            **metadata,
                            "page": page["page"],
                            "section_title": section["title"],
                            "chunk_index": index,
                            "chunk_word_count": word_count(text),
                        }
                        record = {
                            "id": f"{Path(source_name).stem}-p{page['page']}-{count}",
                            "source": source_name,
                            "company_name": metadata.get("company_name"),
                            "document_year": metadata.get("document_year"),
                            "document_period": metadata.get("document_period"),
                            "document_type": metadata.get("document_type"),
                            "page": page["page"],
                            "section_title": section["title"],
                            "chunk_index": index,
                            "metadata": chunk_metadata,
                            "text": text,
                        }
                        target.write(json.dumps(record, ensure_ascii=False) + "\n")
                        count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Split cleaned document pages into chunks.")
    parser.add_argument("--input", default="data/cleaned/cleaned.jsonl", type=Path)
    parser.add_argument("--output", default="data/cleaned/chunks.jsonl", type=Path)
    parser.add_argument("--max-words", default=220, type=int)
    parser.add_argument("--overlap-sentences", default=1, type=int)
    args = parser.parse_args()
    count = build_chunks(args.input, args.output, args.max_words, args.overlap_sentences)
    print(f"Wrote {count} chunk(s) into {args.output}")


if __name__ == "__main__":
    main()
