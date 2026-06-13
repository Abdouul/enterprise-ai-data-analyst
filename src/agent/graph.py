from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any, TypedDict

from dotenv import load_dotenv


GEMINI_MODEL = "gemini-2.5-flash"


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
- The SQL table contains annual figures only. In a mixed question such as
  "revenue in 2024 and risks in the Q3 report", apply 2024 to the SQL query
  but apply Q3 only to the vector search. NEVER add a quarter or Q3 condition
  to the SQL query.
- Revenue and net income are expressed in billions of USD
  (columns revenue_billion_usd and net_income_billion_usd).
- If a query returns 0 rows, broaden the filter (drop the year or use LIKE)
  and try again before giving up.

ALWAYS finish with a clear, written natural-language answer that synthesizes
the numbers from execute_sql and the qualitative evidence from
search_vector_db. Never end your turn with an empty message: if a tool returned
no data, say so explicitly and answer with whatever evidence you have.
"""


def load_environment() -> None:
    """Load environment variables from `.env` and `src/.env`."""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / "src" / ".env")

    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


def has_agent_credentials() -> bool:
    """Return whether the GCP Gemini API key is available."""
    load_environment()
    return bool(os.getenv("GCP_API_KEY"))


def build_chat_model():
    """Build the Gemini 3.5 Flash model used by the LangGraph ReAct loop."""
    load_environment()
    api_key = os.getenv("GCP_API_KEY")
    if not api_key:
        raise RuntimeError("GCP_API_KEY is required to run the Gemini agent.")

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=GEMINI_MODEL, google_api_key=api_key, temperature=0)


def build_react_agent():
    """Build the LangGraph ReAct agent for Phase 2."""
    from langgraph.prebuilt import create_react_agent
    from src.agent.tools_sql import execute_sql
    from src.agent.tools_vector import search_vector_db

    llm = build_chat_model()
    return create_react_agent(llm, tools=[execute_sql, search_vector_db], state_modifier=SYSTEM_PROMPT)


def run_agent(question: str) -> str:
    """Run the LangGraph ReAct agent and return the final answer text."""
    return _run_agent_state(question)["answer"]


def _run_agent_state(question: str) -> AnalystState:
    """Run the agent and preserve SQL/vector tool outputs for the API."""
    agent = build_react_agent()
    try:
        result = agent.invoke({"messages": [("user", question)]})
        from src.agent.cost_tracker import log_cost, tracker_from_messages

        log_cost(tracker_from_messages(result["messages"], GEMINI_MODEL), event="agent_loop")
        context, sql_result = _extract_tool_results(result["messages"])
        return {
            "question": question,
            "context": context,
            "sql_result": sql_result,
            "answer": _content_to_text(result["messages"][-1].content),
        }
    except Exception as exc:
        if is_llm_quota_error(exc):
            return {
                "question": question,
                "context": [],
                "sql_result": None,
                "answer": (
                    "Gemini quota/rate-limit error: your API key is loaded, but the project has no available quota "
                    "or is temporarily rate-limited. Wait for the retry window, enable billing/increase quota, or "
                    "remove the Gemini key to use the local vector-search fallback."
                ),
            }
        raise


def _parse_tool_content(content: object) -> Any:
    """Convert LangChain tool content into its original Python structure."""
    if not isinstance(content, str):
        return content
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(content)
        except (SyntaxError, ValueError):
            return content


def _extract_tool_results(messages: list[object]) -> tuple[list[dict[str, object]], dict[str, object] | None]:
    """Extract the latest vector and SQL results from LangGraph ToolMessages."""
    context: list[dict[str, object]] = []
    sql_result: dict[str, object] | None = None

    for message in messages:
        tool_name = getattr(message, "name", None)
        parsed = _parse_tool_content(getattr(message, "content", None))
        if tool_name == "execute_sql" and isinstance(parsed, dict):
            sql_result = parsed
        elif tool_name == "search_vector_db" and isinstance(parsed, dict):
            results = parsed.get("results", [])
            if isinstance(results, list):
                context = [item for item in results if isinstance(item, dict)]

    return context, sql_result


def _content_to_text(content: object) -> str:
    """Normalize LangChain message content to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
        return "\n".join(parts)
    return str(content)


def is_llm_quota_error(exc: Exception) -> bool:
    """Detect provider quota/rate-limit failures even when wrapped by LangGraph."""
    quota_markers = [
        "insufficient_quota",
        "exceeded your current quota",
        "quota exceeded",
        "rate limit",
        "ratelimit",
        "resource_exhausted",
        "resourceexhausted",
        "429",
    ]

    current: BaseException | None = exc
    while current:
        name = current.__class__.__name__.lower()
        message = str(current).lower()
        if any(marker in name or marker in message for marker in quota_markers):
            return True
        current = current.__cause__ or current.__context__
    return False


def answer_question(question: str, limit: int = 5) -> AnalystState:
    """Compatibility wrapper used by the FastAPI endpoint."""
    if has_agent_credentials():
        return _run_agent_state(question)

    from src.agent.tools_vector import search_vector_db_query

    vector_result = search_vector_db_query(question, limit=limit)
    answer = "Vector context retrieved. Set GCP_API_KEY to run the Gemini agent."
    return {
        "question": question,
        "context": vector_result["results"],
        "sql_result": None,
        "answer": answer,
    }
