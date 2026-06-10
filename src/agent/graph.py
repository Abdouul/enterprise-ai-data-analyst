from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent

from src.agent.tools_sql import execute_sql
from src.agent.tools_vector import search_vector_db_query, search_vector_db

# Load environment variables from src/.env (where GCP_API_KEY is stored).
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Use the OS (Windows) certificate store so corporate proxy CAs are trusted.
# This avoids "CERTIFICATE_VERIFY_FAILED" behind the corporate SSL proxy.
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:
    pass


class AnalystState(TypedDict):
    question: str
    context: list[dict[str, object]]
    answer: str
    sql_result: dict[str, object] | None


SYSTEM_PROMPT = """You are an enterprise AI data analyst.

Use execute_sql for structured numeric questions about revenue, net income,
year, report type, and industry from the local SQLite financials table.
Use search_vector_db for qualitative evidence from financial reports and
earnings transcripts. For mixed questions, use both tools and cite the evidence
you used. If execute_sql returns an error, inspect the schema in the tool output
and try a corrected SELECT query.

The financials table has these columns:
company_name TEXT, year INTEGER, revenue_billion_usd REAL,
net_income_billion_usd REAL, report_type TEXT, industry TEXT.

SQL rules:
- company_name is stored as the full legal name (e.g. 'Apple Inc.',
  'Microsoft Corporation', 'Tesla, Inc.'). NEVER filter with an exact short
  name like company_name = 'Apple'. ALWAYS match partially and
  case-insensitively, e.g. WHERE LOWER(company_name) LIKE '%apple%'.
- Revenue and net income are expressed in billions of USD
  (columns revenue_billion_usd and net_income_billion_usd).
- If a query returns 0 rows, broaden the filter (drop the year or use LIKE)
  and try again before giving up.

ALWAYS finish with a clear, written natural-language answer that synthesizes
the numbers from execute_sql and the qualitative evidence from
search_vector_db. Never end your turn with an empty message: if a tool returned
no data, say so explicitly and answer with whatever evidence you have.
"""


def build_react_agent():
    """Build the LangGraph ReAct agent for Phase 2.

    This requires GCP_API_KEY because the ReAct loop needs an LLM (Google Gemini).
    The tools themselves are local: SQLite for structured data and Qdrant for
    vector data. A lightweight "lite" model is used by default to limit token use.
    """
    api_key = os.getenv("GCP_API_KEY")
    if not api_key:
        raise RuntimeError("GCP_API_KEY is required to run the LangGraph ReAct agent.")

    from langchain_google_genai import ChatGoogleGenerativeAI

    llm = ChatGoogleGenerativeAI(
        model=os.getenv("AGENT_MODEL", "gemini-2.0-flash-lite"),
        google_api_key=api_key,
        temperature=0,
    )
    return create_react_agent(llm, tools=[execute_sql, search_vector_db], state_modifier=SYSTEM_PROMPT)


def run_agent(question: str) -> str:
    """Run the LangGraph ReAct agent and return the final answer text."""
    agent = build_react_agent()
    result = agent.invoke({"messages": [("user", question)]})
    return result["messages"][-1].content


def answer_question(question: str, limit: int = 5) -> AnalystState:
    """Compatibility wrapper used by the FastAPI endpoint.

    If GCP_API_KEY is configured, it runs the full LangGraph ReAct agent.
    Otherwise it performs vector retrieval only so the API remains usable during
    local development.
    """
    if os.getenv("GCP_API_KEY"):
        return {
            "question": question,
            "context": [],
            "sql_result": None,
            "answer": run_agent(question),
        }

    vector_result = search_vector_db_query(question, limit=limit)
    answer = "Vector context retrieved. Set GCP_API_KEY to run the full LangGraph ReAct agent."
    return {
        "question": question,
        "context": vector_result["results"],
        "sql_result": None,
        "answer": answer,
    }
