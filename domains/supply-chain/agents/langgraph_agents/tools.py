"""LangGraph tool wrappers for supply-chain retrieval and synthesis."""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


@tool
def vector_search(question: str, entity_id: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
    """Search Qdrant for supply-chain events matching the question."""
    from app import vector_context
    return vector_context(question, entity_id, top_k)


@tool
def graph_lookup(entity_ids: list[str]) -> list[dict[str, Any]]:
    """Retrieve supplier graph context from Neo4j."""
    from app import graph_context
    return graph_context(entity_ids)


@tool
def classify_request(question: str, entity_id: str | None = None) -> dict[str, str]:
    """Classify a supply-chain question into a request type."""
    from domain import classify_request_type, select_retrieval_plan
    request_type = classify_request_type(question, entity_id)
    plan = select_retrieval_plan(request_type, question, entity_id, 5)
    return {"request_type": request_type, "query_text": plan.query_text, "top_k": plan.top_k, "reason": plan.reason}


@tool
def synthesize_answer(question: str, vector_ctx: list[dict[str, Any]], graph_ctx: list[dict[str, Any]]) -> str:
    """Generate a grounded supply-chain answer."""
    from app import ask_ollama
    return ask_ollama(question, vector_ctx, graph_ctx)


ALL_TOOLS = [vector_search, graph_lookup, classify_request, synthesize_answer]
