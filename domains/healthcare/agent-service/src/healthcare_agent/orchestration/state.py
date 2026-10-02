"""Shared state schema for the LangGraph healthcare multi-agent graph.

Uses TypedDict with Annotated reducer fields so every node can append to
lists independently and LangGraph merges them automatically.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

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
    context_limit: int  # upper bound on retrieved evidence items for this request

    # ── guardrails (input/output policy nodes) ──────────────────────────
    guardrails: dict[str, Any]

    # ── routing / planning ──────────────────────────────────────────────
    request_type: RequestType
    plan_query_text: str
    plan_top_k: int
    plan_reason: str

    # ── retrieval results (append-only via reducer) ─────────────────────
    vector_context: Annotated[list[dict[str, Any]], operator.add]
    graph_context: Annotated[list[dict[str, Any]], operator.add]
    patient_ids: Annotated[list[str], operator.add]

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
