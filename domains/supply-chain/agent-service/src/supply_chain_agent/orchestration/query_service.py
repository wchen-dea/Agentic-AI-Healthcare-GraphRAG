"""Application service for question answering over the LangGraph orchestrator.

Transport layers (HTTP routes, MCP tools, evaluation) call this service
instead of the graph directly so the evidence budget is applied uniformly.
"""
from __future__ import annotations

from typing import Any

from supply_chain_agent.orchestration.graph import run_langgraph_query


class QueryService:
    def __init__(self, *, max_context_items: int) -> None:
        self._max_context_items = max_context_items

    def context_limit(self, top_k: int | None) -> int:
        return min(top_k or self._max_context_items, max(self._max_context_items, 8))

    def run_query(self, question: str, entity_id: str | None = None, top_k: int | None = None) -> dict[str, Any]:
        return run_langgraph_query(question, entity_id, context_limit=self.context_limit(top_k))
