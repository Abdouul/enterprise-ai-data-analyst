from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.agent.graph import answer_question


app = FastAPI(title="Enterprise AI Data Analyst", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    limit: int = Field(default=5, ge=1, le=20)


@app.get("/")
def root() -> dict[str, str]:
    """Describe the API and expose its main endpoints."""
    return {
        "service": "Enterprise AI Data Analyst",
        "status": "running",
        "documentation": "/docs",
        "health": "/health",
        "ask": "POST /ask",
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask")
def ask(request: AskRequest) -> dict[str, object]:
    return answer_question(request.question, limit=request.limit)
