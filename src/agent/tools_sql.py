from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = Path(db_path or os.getenv("FINANCE_DB_PATH", "data/finance.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def run_readonly_query(query: str, db_path: str | None = None) -> list[dict[str, object]]:
    normalized = query.strip().lower()
    if not normalized.startswith("select"):
        raise ValueError("Only SELECT queries are allowed")

    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(query)
        return [dict(row) for row in cursor.fetchall()]
