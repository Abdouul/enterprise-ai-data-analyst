from __future__ import annotations

import re
from pathlib import Path


COMPANY_ALIASES = {
    "alphabet": "Alphabet Inc.",
    "amazon": "Amazon.com, Inc.",
    "apple": "Apple Inc.",
    "exxonmobil": "Exxon Mobil Corporation",
    "goldman_sachs": "Goldman Sachs Group, Inc.",
    "meta_platforms": "Meta Platforms, Inc.",
    "microsoft": "Microsoft Corporation",
    "nvidia": "NVIDIA Corporation",
    "pfizer": "Pfizer Inc.",
    "tesla": "Tesla, Inc.",
}


def infer_metadata(path: Path, text: str = "") -> dict[str, object]:
    """Infer structured metadata from the file name and document preview.

    Qdrant stores this metadata with every vector so the analyst can filter or
    cite results by company, year, period, document type, and source file.
    """
    stem = path.stem.lower()
    searchable = f"{stem}\n{text[:1000]}".lower()

    company_key = next((key for key in COMPANY_ALIASES if key in searchable), path.stem.split("_")[0])
    year_match = re.search(r"(?:fy|q[1-4]_?|year\s*)?(20\d{2}|fy202\d)", searchable)
    quarter_match = re.search(r"\b(q[1-4])\b", searchable)

    document_type = "financial_report"
    if "transcript" in searchable:
        document_type = "earnings_call_transcript"
    elif "10k" in searchable or "10-k" in searchable:
        document_type = "annual_10k"
    elif "risk" in searchable:
        document_type = "risk_factors"
    elif "shareholder" in searchable:
        document_type = "shareholder_letter"
    elif "annual" in searchable:
        document_type = "annual_report"
    elif "release" in searchable:
        document_type = "earnings_release"

    year = None
    if year_match:
        year = int(year_match.group(1).replace("fy", ""))

    period = quarter_match.group(1).upper() if quarter_match else None
    if "fy" in searchable and period is None:
        period = "FY"

    return {
        "company_name": COMPANY_ALIASES.get(company_key, company_key.replace("_", " ").title()),
        "document_year": year,
        "document_period": period,
        "document_type": document_type,
        "source_file": path.name,
        "source_path": str(path),
    }
