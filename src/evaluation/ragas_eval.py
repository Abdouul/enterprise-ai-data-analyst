from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def load_eval_dataset(path: Path) -> pd.DataFrame:
    if path.suffix == ".csv":
        return pd.read_csv(path)
    if path.suffix in {".json", ".jsonl"}:
        return pd.read_json(path, lines=path.suffix == ".jsonl")
    raise ValueError("Evaluation dataset must be .csv, .json or .jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(description="Load an evaluation dataset for RAGAS experiments.")
    parser.add_argument("--dataset", required=True, type=Path)
    args = parser.parse_args()
    dataset = load_eval_dataset(args.dataset)
    required_columns = {"question", "answer", "contexts", "ground_truth"}
    missing = required_columns.difference(dataset.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    print(f"Loaded {len(dataset)} evaluation row(s)")


if __name__ == "__main__":
    main()
