"""Application service for question answering over the LangGraph orchestrator.

Owns request-level concerns that sit around the graph: the evidence budget
(``context_limit``) and conversation memory. Transport layers (HTTP routes,
MCP tools, evaluation gates) call this service instead of the graph directly.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from healthcare_agent.orchestration.graph import run_langgraph_query, stream_langgraph_query
from healthcare_agent.orchestration.memory import get_session_store


class QueryService:
    def __init__(self, *, max_context_items: int) -> None:
        self._max_context_items = max_context_items

    def context_limit(self, top_k: int | None) -> int:
        return min(top_k or self._max_context_items, max(self._max_context_items, 8))

    @staticmethod
    def load_session_context(session_id: str | None) -> str:
        if not session_id:
            return ""
        return get_session_store().get_or_create(session_id).get_context_summary()

    @staticmethod
    def remember_turn(
        session_id: str | None, question: str, result: dict[str, Any], patient_id: str | None
    ) -> None:
        if not session_id or (result.get("guardrails") or {}).get("input_blocked"):
            return
        store = get_session_store()
        session = store.get_or_create(session_id)
        session.add_turn(question=question, answer=result.get("answer", ""), patient_id=patient_id)
        if hasattr(store, "save"):
            store.save(session)

    def run_query(
        self,
        question: str,
        patient_id: str | None = None,
        top_k: int | None = None,
        structured: bool = False,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        result = run_langgraph_query(
            question=question,
            patient_id=patient_id,
            structured=structured,
            session_context=self.load_session_context(session_id),
            context_limit=self.context_limit(top_k),
        )
        self.remember_turn(session_id, question, result, patient_id)
        return result

    def stream(
        self,
        question: str,
        patient_id: str | None = None,
        *,
        structured: bool = False,
        session_id: str | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield graph ``step`` events, then the ``result``; the turn is remembered on result."""
        for kind, data in stream_langgraph_query(
            question,
            patient_id,
            structured=structured,
            session_context=self.load_session_context(session_id),
            context_limit=self.context_limit(None),
        ):
            if kind == "result":
                self.remember_turn(session_id, question, data, patient_id)
            yield kind, data
