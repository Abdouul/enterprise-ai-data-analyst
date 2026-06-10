from __future__ import annotations

import os
from pathlib import Path
from typing import TypedDict

from dotenv import load_dotenv


GEMINI_TOOL_MODEL_FALLBACK = "gemini-1.5-flash"


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


def load_environment() -> None:
    """Load environment variables from `.env` and `src/.env`."""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / "src" / ".env")

    gemini_key = os.getenv("GEMINI_API_KEY") or os.getenv("GCP_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if gemini_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gemini_key

    try:
        import truststore

        truststore.inject_into_ssl()
    except Exception:
        pass


def has_agent_credentials() -> bool:
    """Return whether the configured LLM provider has credentials available."""
    load_environment()
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "openai":
        return bool(os.getenv("OPENAI_API_KEY"))
    return bool(os.getenv("GOOGLE_API_KEY"))


def select_gemini_tool_model() -> str:
    """Select a Gemini model compatible with LangGraph tool calling."""
    requested_model = os.getenv("AGENT_MODEL", GEMINI_TOOL_MODEL_FALLBACK).strip()
    model_lower = requested_model.lower()
    if model_lower.startswith("gemini-3") or model_lower.startswith("gemini-2.5"):
        print(
            f"[agent.graph] {requested_model} requires thought signatures for tool calls; "
            f"using {GEMINI_TOOL_MODEL_FALLBACK} for LangGraph ReAct tools."
        )
        return GEMINI_TOOL_MODEL_FALLBACK
    return requested_model


def build_chat_model():
    """Build the chat model used by the LangGraph ReAct loop."""
    load_environment()
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "openai":
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required when LLM_PROVIDER=openai.")
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=os.getenv("AGENT_MODEL", "gpt-4o-mini"), temperature=0)

    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY, GOOGLE_API_KEY, or GCP_API_KEY is required to run the Gemini agent.")

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(model=select_gemini_tool_model(), temperature=0)


def build_react_agent():
    """Build the LangGraph ReAct agent for Phase 2."""
    from langgraph.prebuilt import create_react_agent
    from src.agent.tools_sql import execute_sql
    from src.agent.tools_vector import search_vector_db

    llm = build_chat_model()
    return create_react_agent(llm, tools=[execute_sql, search_vector_db], state_modifier=SYSTEM_PROMPT)


def run_agent(question: str) -> str:
    """Run the LangGraph ReAct agent and return the final answer text."""
    agent = build_react_agent()
    try:
        result = agent.invoke({"messages": [("user", question)]})
        return _content_to_text(result["messages"][-1].content)
    except Exception as exc:
        if is_llm_quota_error(exc):
            return (
                "Gemini quota/rate-limit error: your API key is loaded, but the project has no available quota "
                "or is temporarily rate-limited. Wait for the retry window, enable billing/increase quota, or "
                "remove the Gemini key to use the local vector-search fallback."
            )
        raise


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
        return {
            "question": question,
            "context": [],
            "sql_result": None,
            "answer": run_agent(question),
        }

    from src.agent.tools_vector import search_vector_db_query

    vector_result = search_vector_db_query(question, limit=limit)
    answer = "Vector context retrieved. Set GEMINI_API_KEY, GOOGLE_API_KEY, or GCP_API_KEY to run the Gemini agent."
    return {
        "question": question,
        "context": vector_result["results"],
        "sql_result": None,
        "answer": answer,
    }
