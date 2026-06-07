from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def clean_jsonl(input_file: Path, output_file: Path) -> int:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with input_file.open("r", encoding="utf-8") as source, output_file.open("w", encoding="utf-8") as target:
        for line in source:
            document = json.loads(line)
            for page in document.get("pages", []):
                page["text"] = normalize_text(page.get("text", ""))
            target.write(json.dumps(document, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean parsed PDF JSONL text.")
    parser.add_argument("--input", default="data/cleaned/parsed.jsonl", type=Path)
    parser.add_argument("--output", default="data/cleaned/cleaned.jsonl", type=Path)
    args = parser.parse_args()
    count = clean_jsonl(args.input, args.output)
    print(f"Cleaned {count} document(s) into {args.output}")


if __name__ == "__main__":
    main()
