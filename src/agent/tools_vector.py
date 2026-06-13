from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.tools import tool
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue


DEFAULT_MODEL = os.getenv("EMBEDDING_MODEL_PATH", "sentence-transformers/all-MiniLM-L6-v2")


class VectorSearchFilters(BaseModel):
    """Strict metadata filters extracted before vector search."""

    company_name: str | None = Field(default=None, description="Exact company name, e.g. Apple Inc.")
    document_year: int | None = Field(default=None, ge=2000, le=2100)
    document_period: str | None = Field(default=None, description="Quarter or fiscal period, e.g. Q1, Q2, Q3, Q4, FY")
    document_type: str | None = Field(
        default=None,
        description="Document type, e.g. annual_report, earnings_release, earnings_call_transcript, annual_10k",
    )


COMPANY_PATTERNS = {
    "alphabet": "Alphabet Inc.",
    "google": "Alphabet Inc.",
    "amazon": "Amazon.com, Inc.",
    "apple": "Apple Inc.",
    "exxon": "Exxon Mobil Corporation",
    "exxonmobil": "Exxon Mobil Corporation",
    "goldman": "Goldman Sachs Group, Inc.",
    "meta": "Meta Platforms, Inc.",
    "facebook": "Meta Platforms, Inc.",
    "microsoft": "Microsoft Corporation",
    "nvidia": "NVIDIA Corporation",
    "pfizer": "Pfizer Inc.",
    "tesla": "Tesla, Inc.",
}


def extract_filters_with_instructor(query: str) -> VectorSearchFilters | None:
    """Use a lite Gemini model to extract strict Pydantic filters."""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")
    load_dotenv(project_root / "src" / ".env")
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or os.getenv("GCP_API_KEY")
    if not api_key:
        return None
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
    except ImportError:
        return None

    try:
        model = os.getenv("FILTER_EXTRACTION_MODEL", "gemini-2.5-flash-lite")
        llm = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=api_key,
            temperature=0,
        )
        structured = llm.with_structured_output(VectorSearchFilters, include_raw=True)
        response = structured.invoke(
            "Extract only explicit metadata filters from the user query. "
            "Leave unknown fields null.\n\nQuery: " + query
        )
        raw_message = response.get("raw")
        if raw_message is not None:
            from src.agent.cost_tracker import log_cost, tracker_from_messages

            log_cost(tracker_from_messages([raw_message], model), event="metadata_filter")
        return response.get("parsed")
    except Exception:
        return None


def extract_filters_heuristic(query: str) -> VectorSearchFilters:
    """Fallback Pydantic filter extraction when Instructor/LLM is unavailable."""
    lowered = query.lower()
    company_name = next((company for key, company in COMPANY_PATTERNS.items() if key in lowered), None)
    year_match = re.search(r"\b(20\d{2})\b", lowered)
    period_match = re.search(r"\b(q[1-4]|fy)\b", lowered)

    document_type = None
    if "10-k" in lowered or "10k" in lowered:
        document_type = "annual_10k"
    elif "transcript" in lowered or "call" in lowered:
        document_type = "earnings_call_transcript"
    elif "release" in lowered:
        document_type = "earnings_release"
    elif "annual" in lowered:
        document_type = "annual_report"
    elif "risk factors" in lowered:
        document_type = "risk_factors"

    return VectorSearchFilters(
        company_name=company_name,
        document_year=int(year_match.group(1)) if year_match else None,
        document_period=period_match.group(1).upper() if period_match else None,
        document_type=document_type,
    )


def extract_metadata_filters(query: str) -> VectorSearchFilters:
    """Extract strict Pydantic metadata filters before semantic search."""
    filters = extract_filters_with_instructor(query) or extract_filters_heuristic(query)
    if filters.company_name:
        normalized_name = normalize_company_name(filters.company_name)
        filters = filters.model_copy(update={"company_name": normalized_name})
    return filters


def normalize_company_name(company_name: str) -> str:
    """Map an extracted company alias to the exact name stored in Qdrant."""
    lowered = company_name.lower()
    for alias, canonical_name in COMPANY_PATTERNS.items():
        if alias in lowered or lowered in canonical_name.lower():
            return canonical_name
    return company_name


def to_qdrant_filter(filters: VectorSearchFilters) -> Filter | None:
    """Convert Pydantic filters into a Qdrant metadata filter."""
    conditions = []
    for key, value in filters.model_dump(exclude_none=True).items():
        conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))
    return Filter(must=conditions) if conditions else None


class VectorSearchTool:
    def __init__(
        self,
        qdrant_url: str | None = None,
        collection: str | None = None,
        model_name: str = DEFAULT_MODEL,
    ) -> None:
        """Initialize Qdrant and the local embedding model."""
        from sentence_transformers import SentenceTransformer

        self.collection = collection or os.getenv("QDRANT_COLLECTION", "finance_docs")
        qdrant_path = os.getenv("QDRANT_PATH")
        self.client = (
            QdrantClient(path=qdrant_path)
            if qdrant_path
            else QdrantClient(url=qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333"))
        )
        self.model = SentenceTransformer(model_name)

    def close(self) -> None:
        """Release the Qdrant client, including local storage file locks."""
        self.client.close()

    def search(self, query: str, limit: int = 5, filters: VectorSearchFilters | None = None) -> list[dict[str, object]]:
        """Search Qdrant semantically after applying metadata filters."""
        vector = self.model.encode(query).tolist()
        query_filter = to_qdrant_filter(filters) if filters else None
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=query_filter,
            limit=limit,
        )
        return [
            {
                "score": result.score,
                "source": result.payload.get("source"),
                "company_name": result.payload.get("company_name"),
                "document_year": result.payload.get("document_year"),
                "document_type": result.payload.get("document_type"),
                "page": result.payload.get("page"),
                "section_title": result.payload.get("section_title"),
                "text": result.payload.get("text"),
            }
            for result in results
        ]


def search_vector_db_query(query: str, limit: int = 5) -> dict[str, Any]:
    """Extract filters, search Qdrant, and relax over-specific filters if needed."""
    filters = extract_metadata_filters(query)
    vector_tool = VectorSearchTool()
    try:
        results = vector_tool.search(query, limit=limit, filters=filters)
        applied_filters = filters
        relaxed_fields: list[str] = []

        # LLM extraction can infer a semantic document type (for example
        # "risk_factors") that differs from the source document's stored type
        # ("financial_report"). Keep company/year/period and relax type first.
        if not results and filters.document_type is not None:
            applied_filters = filters.model_copy(update={"document_type": None})
            relaxed_fields.append("document_type")
            results = vector_tool.search(query, limit=limit, filters=applied_filters)

        # If the dataset uses fiscal periods differently, retry without period while
        # retaining the strongest filters: company and year.
        if not results and applied_filters.document_period is not None:
            applied_filters = applied_filters.model_copy(update={"document_period": None})
            relaxed_fields.append("document_period")
            results = vector_tool.search(query, limit=limit, filters=applied_filters)

        return {
            "filters": applied_filters.model_dump(exclude_none=True),
            "relaxed_fields": relaxed_fields,
            "results": results,
            "result_count": len(results),
        }
    finally:
        vector_tool.close()


@tool
def search_vector_db(query: str, limit: int = 5) -> dict[str, Any]:
    """Search Qdrant for unstructured report/transcript evidence."""
    return search_vector_db_query(query, limit=limit)
