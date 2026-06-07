from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


FINANCIAL_ROWS = [
    {
        "company_name": "Alphabet Inc.",
        "year": 2024,
        "revenue_billion_usd": 80.5,
        "net_income_billion_usd": 23.7,
        "report_type": "Q1 earnings call transcript",
        "industry": "Technology",
    },
    {
        "company_name": "Amazon.com, Inc.",
        "year": 2024,
        "revenue_billion_usd": 148.0,
        "net_income_billion_usd": 13.5,
        "report_type": "Q2 earnings release",
        "industry": "E-commerce and Cloud",
    },
    {
        "company_name": "Apple Inc.",
        "year": 2024,
        "revenue_billion_usd": 85.8,
        "net_income_billion_usd": 21.4,
        "report_type": "Q3 earnings report",
        "industry": "Consumer Electronics",
    },
    {
        "company_name": "Exxon Mobil Corporation",
        "year": 2024,
        "revenue_billion_usd": 93.1,
        "net_income_billion_usd": 9.2,
        "report_type": "Q2 earnings report",
        "industry": "Energy",
    },
    {
        "company_name": "Goldman Sachs Group, Inc.",
        "year": 2023,
        "revenue_billion_usd": 46.3,
        "net_income_billion_usd": 8.5,
        "report_type": "2023 10-K risk factors",
        "industry": "Financial Services",
    },
    {
        "company_name": "Meta Platforms, Inc.",
        "year": 2023,
        "revenue_billion_usd": 134.9,
        "net_income_billion_usd": 39.1,
        "report_type": "FY2023 annual review",
        "industry": "Social Media and Advertising",
    },
    {
        "company_name": "Microsoft Corporation",
        "year": 2024,
        "revenue_billion_usd": 245.1,
        "net_income_billion_usd": 88.1,
        "report_type": "FY2024 annual report",
        "industry": "Software and Cloud",
    },
    {
        "company_name": "NVIDIA Corporation",
        "year": 2025,
        "revenue_billion_usd": 26.0,
        "net_income_billion_usd": 14.9,
        "report_type": "Q1 FY2025 earnings transcript",
        "industry": "Semiconductors",
    },
    {
        "company_name": "Pfizer Inc.",
        "year": 2023,
        "revenue_billion_usd": 58.5,
        "net_income_billion_usd": 2.1,
        "report_type": "FY2023 annual results",
        "industry": "Pharmaceuticals",
    },
    {
        "company_name": "Tesla, Inc.",
        "year": 2023,
        "revenue_billion_usd": 96.8,
        "net_income_billion_usd": 15.0,
        "report_type": "Q4 FY2023 shareholder letter",
        "industry": "Automotive and Energy",
    },
]


def create_finance_db(db_path: Path) -> int:
    """Create the local SQLite database used for structured financial questions.

    The agent will later use this table when a user asks for numeric facts such
    as revenue, net income, year, report type, or industry. The function drops
    and recreates the table so the database is reproducible every time Phase 1
    runs.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE IF EXISTS financials")
        connection.execute(
            """
            CREATE TABLE financials (
                company_name TEXT NOT NULL,
                year INTEGER NOT NULL,
                revenue_billion_usd REAL NOT NULL,
                net_income_billion_usd REAL NOT NULL,
                report_type TEXT NOT NULL,
                industry TEXT NOT NULL,
                PRIMARY KEY (company_name, year, report_type)
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO financials (
                company_name,
                year,
                revenue_billion_usd,
                net_income_billion_usd,
                report_type,
                industry
            )
            VALUES (
                :company_name,
                :year,
                :revenue_billion_usd,
                :net_income_billion_usd,
                :report_type,
                :industry
            )
            """,
            FINANCIAL_ROWS,
        )
    return len(FINANCIAL_ROWS)


def main() -> None:
    """Expose database creation as a command-line script."""
    parser = argparse.ArgumentParser(description="Create the SQLite finance database used by the SQL agent.")
    parser.add_argument("--db-path", default="data/finance.db", type=Path)
    args = parser.parse_args()
    count = create_finance_db(args.db_path)
    print(f"Created {args.db_path} with {count} financial row(s)")


if __name__ == "__main__":
    main()
