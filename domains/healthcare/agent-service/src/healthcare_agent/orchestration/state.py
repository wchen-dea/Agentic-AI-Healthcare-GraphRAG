"""Shared state schema for the LangGraph healthcare multi-agent graph.

Uses TypedDict with Annotated reducer fields so every node can append to
lists independently and LangGraph merges them automatically.
"""
from __future__ import annotations

import json
import operator
from typing import Annotated, Any, Literal, TypedDict

_IDENTITY_KEYS = ("event_id", "id", "patient_id")


def _item_key(item: Any) -> str:
    if isinstance(item, dict):
        for key in _IDENTITY_KEYS:
            value = item.get(key)
            if value is not None:
                return f"{key}:{value}"
        return "json:" + json.dumps(item, sort_keys=True, default=str)
    return f"{type(item).__name__}:{item}"


def merge_unique(left: list[Any] | None, right: list[Any] | None) -> list[Any]:
    """Append-only reducer that drops items already present (first wins).

    Re-retrieval passes return overlapping evidence; plain ``operator.add``
    would duplicate it and inflate the synthesis context on every iteration.
    """
    merged = list(left or [])
    seen = {_item_key(item) for item in merged}
    for item in right or []:
        key = _item_key(item)
        if key not in seen:
            seen.add(key)
            merged.append(item)
    return merged

RequestType = Literal[
    "patient_summary",
    "medication_safety",
    "lab_interpretation",
    "coding_review",
    "cohort_triage",
]


class HealthcareAgentState(TypedDict, total=False):
    # ── immutable inputs ────────────────────────────────────────────────
    question: str
    patient_id: str | None
    structured: bool
    # Prior-turn summary from session memory; used only for synthesis prompts.
    session_context: str
    # Governed, patient-scoped durable memory; never used as session history.
    patient_memory_context: Annotated[list[dict[str, Any]], merge_unique]
    patient_memory_facts: Annotated[list[dict[str, Any]], merge_unique]
    patient_memory_policy: dict[str, Any]
    patient_memory_metadata: dict[str, Any]
    # Internal application-to-graph handoff; never exposed as prompt text.
    _patient_memory_record: Any
    context_limit: int  # upper bound on retrieved evidence items for this request

    # ── guardrails (input/output policy nodes) ──────────────────────────
    guardrails: dict[str, Any]

    # ── routing / planning ──────────────────────────────────────────────
    request_type: RequestType
    plan_query_text: str
    plan_top_k: int
    plan_reason: str

    # ── retrieval results (append-only, deduplicated across iterations) ─
    vector_context: Annotated[list[dict[str, Any]], merge_unique]
    graph_context: Annotated[list[dict[str, Any]], merge_unique]
    patient_ids: Annotated[list[str], merge_unique]

    # ── agent reasoning trace (append-only) ─────────────────────────────
    messages: Annotated[list[dict[str, Any]], operator.add]

    # ── inter-agent delegation (append-only) ────────────────────────────
    delegation_requests: Annotated[list[dict[str, Any]], operator.add]
    delegation_responses: Annotated[list[dict[str, Any]], operator.add]

    # ── synthesis ───────────────────────────────────────────────────────
    answer: str
    structured_response: dict[str, Any]
    confidence: float
    iteration: int
    final_reason: str
    review_required: bool
    human_review: dict[str, Any]
