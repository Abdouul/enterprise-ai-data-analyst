from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv
from langgraph.prebuilt import create_react_agent

from src.agent.tools_sql import execute_sql
from src.agent.tools_vector import search_vector_db_query, search_vector_db

# Load environment variables from src/.env (where OPENAI_API_KEY is stored).
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
"""


def build_react_agent():
    """Build the LangGraph ReAct agent for Phase 2.

    This requires OPENAI_API_KEY because the ReAct loop needs an LLM. The tools
    themselves are local: SQLite for structured data and Qdrant for vector data.
    """
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("OPENAI_API_KEY is required to run the LangGraph ReAct agent.")

    from langchain_openai import ChatOpenAI

    llm = ChatOpenAI(model=os.getenv("AGENT_MODEL", "gpt-4o-mini"), temperature=0)
    return create_react_agent(llm, tools=[execute_sql, search_vector_db], state_modifier=SYSTEM_PROMPT)


def run_agent(question: str) -> str:
    """Run the LangGraph ReAct agent and return the final answer text."""
    agent = build_react_agent()
    result = agent.invoke({"messages": [("user", question)]})
    return result["messages"][-1].content


def answer_question(question: str, limit: int = 5) -> AnalystState:
    """Compatibility wrapper used by the FastAPI endpoint.

    If OPENAI_API_KEY is configured, it runs the full LangGraph ReAct agent.
    Otherwise it performs vector retrieval only so the API remains usable during
    local development.
    """
    if os.getenv("OPENAI_API_KEY"):
        return {
            "question": question,
            "context": [],
            "sql_result": None,
            "answer": run_agent(question),
        }

    vector_result = search_vector_db_query(question, limit=limit)
    answer = "Vector context retrieved. Set OPENAI_API_KEY to run the full LangGraph ReAct agent."
    return {
        "question": question,
        "context": vector_result["results"],
        "sql_result": None,
        "answer": answer,
    }
