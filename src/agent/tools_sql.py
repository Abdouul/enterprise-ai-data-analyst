from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from langchain_core.tools import tool


SQL_SCHEMA = """
Table: financials
Columns:
- company_name TEXT
- year INTEGER
- revenue_billion_usd REAL
- net_income_billion_usd REAL
- report_type TEXT
- industry TEXT
"""


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """Open the local SQLite database used by the SQL agent tool."""
    path = Path(db_path or os.getenv("FINANCE_DB_PATH", "data/finance.db"))
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(path)


def run_readonly_query(query: str, db_path: str | None = None) -> list[dict[str, object]]:
    """Run a safe read-only SQL query and return rows as dictionaries."""
    normalized = query.strip().lower()
    if not normalized.startswith("select"):
        raise ValueError("Only SELECT queries are allowed")

    with get_connection(db_path) as connection:
        connection.row_factory = sqlite3.Row
        cursor = connection.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def repair_sql_query(query: str, error: str) -> str | None:
    """Apply small deterministic repairs before returning an SQL error.

    The ReAct agent can also recover by seeing the error and trying a new query.
    This helper handles common beginner mistakes quickly: wrong table name,
    missing LIMIT, and accidental markdown SQL fences.
    """
    repaired = query.strip().removeprefix("```sql").removeprefix("```").removesuffix("```").strip()
    lowered_error = error.lower()

    if "no such table" in lowered_error:
        repaired = repaired.replace("financial_metrics", "financials").replace("finance", "financials")
    if "no such column" in lowered_error:
        column_aliases = {
            "revenue": "revenue_billion_usd",
            "net_income": "net_income_billion_usd",
            "company": "company_name",
        }
        for wrong, right in column_aliases.items():
            repaired = repaired.replace(wrong, right)

    return repaired if repaired != query.strip() else None


def execute_sql_query(query: str, db_path: str | None = None, max_retries: int = 2) -> dict[str, Any]:
    """Execute SQL with an error-recovery loop for the agent.

    On failure, the tool tries a small deterministic repair. If it still fails,
    it returns the error plus the table schema so the ReAct agent can reason and
    call the tool again with corrected SQL.
    """
    attempts: list[dict[str, str]] = []
    current_query = query

    for _ in range(max_retries + 1):
        try:
            rows = run_readonly_query(current_query, db_path=db_path)
            return {
                "ok": True,
                "query": current_query,
                "rows": rows,
                "row_count": len(rows),
                "attempts": attempts,
            }
        except (sqlite3.Error, ValueError) as exc:
            error = str(exc)
            attempts.append({"query": current_query, "error": error})
            repaired = repair_sql_query(current_query, error)
            if repaired is None or repaired == current_query:
                break
            current_query = repaired

    return {
        "ok": False,
        "query": current_query,
        "error": attempts[-1]["error"] if attempts else "Unknown SQL error",
        "attempts": attempts,
        "schema": SQL_SCHEMA,
        "hint": "Use only SELECT queries against the financials table.",
    }


@tool
def execute_sql(query: str) -> dict[str, Any]:
    """Query the local SQLite financials table for structured numeric data."""
    return execute_sql_query(query)
