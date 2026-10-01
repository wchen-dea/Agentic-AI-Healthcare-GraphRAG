"""Shape orchestration results into role-sanitized, budgeted API payloads."""
from __future__ import annotations

from typing import Any

from agent_core.audit import utc_timestamp

from supply_chain_agent.config.settings import SupplyChainAgentSettings
from supply_chain_agent.safety.response_policy import (
    apply_response_budget,
    sanitize_graph_context_for_role,
    sanitize_vector_context_for_role,
    truncate_text,
    vector_text_mode,
)

_GUARDRAIL_FLAGS = ("input_blocked", "output_blocked", "category")


class ResponseShaper:
    def __init__(self, settings: SupplyChainAgentSettings) -> None:
        self._settings = settings

    def truncate_answer(self, answer: Any) -> str:
        return truncate_text(str(answer or ""), self._settings.max_answer_chars)

    def budget(self, payload: dict[str, Any]) -> dict[str, Any]:
        return apply_response_budget(payload, max_response_bytes=self._settings.max_response_bytes)

    def guardrails(self, caller_role: str, *, include_raw_payload: bool = False) -> dict[str, Any]:
        text_mode = vector_text_mode(caller_role, include_raw_payload=include_raw_payload)
        return {
            "evidence_text_redacted": text_mode != "bounded",
            "evidence_access_level": text_mode,
            "graph_access_level": "broader" if caller_role == "export" else "standard",
            "max_context_items": self._settings.max_context_items,
            "max_response_bytes": self._settings.max_response_bytes,
            "response_truncated": False,
        }

    def sanitize_vector(
        self, items: list[dict[str, Any]], *, caller_role: str, include_raw_payload: bool = False
    ) -> list[dict[str, Any]]:
        return sanitize_vector_context_for_role(
            items,
            caller_role=caller_role,
            include_raw_payload=include_raw_payload,
            max_context_items=self._settings.max_context_items,
            max_evidence_chars=self._settings.max_evidence_chars,
        )

    def sanitize_graph(self, items: list[dict[str, Any]], *, caller_role: str) -> list[dict[str, Any]]:
        return sanitize_graph_context_for_role(
            items,
            caller_role=caller_role,
            max_evidence_chars=self._settings.max_evidence_chars,
            max_context_items=self._settings.max_context_items,
        )

    def query_response(
        self, result: dict[str, Any], trace_id: str, *, caller_role: str, include_raw_payload: bool = False
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "question": result["question"],
            "request_type": result.get("request_type"),
            "retrieval_plan": result.get("retrieval_plan"),
            "entities": result.get("entities", []),
            "vector_context": self.sanitize_vector(
                result.get("vector_context", []), caller_role=caller_role, include_raw_payload=include_raw_payload
            ),
            "graph_context": self.sanitize_graph(result.get("graph_context", []), caller_role=caller_role),
            "answer": self.truncate_answer(result.get("answer")),
            "confidence": result.get("confidence", 0.0),
            "retrieved_at": utc_timestamp(),
            "trace_id": trace_id,
            "guardrails": self.guardrails(caller_role, include_raw_payload=include_raw_payload),
        }
        result_guardrails = result.get("guardrails") or {}
        for flag in _GUARDRAIL_FLAGS:
            if flag in result_guardrails:
                payload["guardrails"][flag] = result_guardrails[flag]
        if result.get("langgraph"):
            payload["langgraph"] = result["langgraph"]
        return self.budget(payload)
