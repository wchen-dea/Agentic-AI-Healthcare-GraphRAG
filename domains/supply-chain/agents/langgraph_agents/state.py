"""Shared state schema for the LangGraph supply-chain multi-agent graph."""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict


RequestType = Literal[
    "supplier_risk",
    "shipment_tracking",
    "quality_review",
    "disruption_impact",
    "inventory_planning",
    "procurement_overview",
]


class SupplyChainAgentState(TypedDict, total=False):
    question: str
    entity_id: str | None

    request_type: RequestType
    plan_query_text: str
    plan_top_k: int
    plan_reason: str

    vector_context: Annotated[list[dict[str, Any]], operator.add]
    graph_context: Annotated[list[dict[str, Any]], operator.add]
    entity_ids: Annotated[list[str], operator.add]
    messages: Annotated[list[dict[str, Any]], operator.add]

    answer: str
    confidence: float
    iteration: int
    final_reason: str
