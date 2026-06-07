from __future__ import annotations

from typing import TypedDict

from src.agent.tools_vector import VectorSearchTool


class AnalystState(TypedDict):
    question: str
    context: list[dict[str, object]]
    answer: str


def answer_question(question: str, limit: int = 5) -> AnalystState:
    vector_tool = VectorSearchTool()
    context = vector_tool.search(question, limit=limit)
    answer = "Context retrieved. Connect an LLM here to synthesize the final response."
    return {"question": question, "context": context, "answer": answer}
