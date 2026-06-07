from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


LINE_SPACE_RE = re.compile(r"[ \t]+")
BLANK_LINES_RE = re.compile(r"\n{3,}")
MOJIBAKE_REPLACEMENTS = {
    "â€”": "-",
    "â€“": "-",
    "â€˜": "'",
    "â€™": "'",
    "â€œ": '"',
    "â€": '"',
    "â€": '"',
    "Â": "",
}


def repair_mojibake(text: str) -> str:
    """Repair common broken UTF-8 text when files were decoded incorrectly."""
    if "â" not in text and "Â" not in text:
        return text
    try:
        return text.encode("cp1252").decode("utf-8")
    except UnicodeError:
        return text


def normalize_text(text: str) -> str:
    """Normalize one text block before chunking and embedding.

    Clean text improves retrieval quality: embeddings are more stable when null
    bytes, inconsistent line endings, excessive whitespace, and broken symbols
    are removed before vectorization.
    """
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = repair_mojibake(text)
    for broken, replacement in MOJIBAKE_REPLACEMENTS.items():
        text = text.replace(broken, replacement)
    lines = [LINE_SPACE_RE.sub(" ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def clean_jsonl(input_file: Path, output_file: Path) -> int:
    """Clean every parsed document in a JSONL file and write cleaned JSONL."""
    output_file.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with input_file.open("r", encoding="utf-8") as source, output_file.open("w", encoding="utf-8") as target:
        for line in source:
            document = json.loads(line)
            for page in document.get("pages", []):
                page["text"] = normalize_text(page.get("text", ""))
            document["cleaning"] = {
                "normalized_whitespace": True,
                "removed_null_bytes": True,
                "repaired_common_mojibake": True,
            }
            target.write(json.dumps(document, ensure_ascii=False) + "\n")
            count += 1
    return count


def main() -> None:
    """Expose text cleaning as a command-line script."""
    parser = argparse.ArgumentParser(description="Clean parsed document JSONL text.")
    parser.add_argument("--input", default="data/cleaned/parsed.jsonl", type=Path)
    parser.add_argument("--output", default="data/cleaned/cleaned.jsonl", type=Path)
    args = parser.parse_args()
    count = clean_jsonl(args.input, args.output)
    print(f"Cleaned {count} document(s) into {args.output}")


if __name__ == "__main__":
    main()
