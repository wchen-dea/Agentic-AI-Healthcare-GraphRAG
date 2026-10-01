"""Shared state schema for the supply-chain LangGraph multi-agent graph."""
from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict

from supply_chain_agent.orchestration.models import RequestType


class SupplyChainAgentState(TypedDict, total=False):
    question: str
    entity_id: str | None
    context_limit: int

    request_type: RequestType
    plan_query_text: str
    plan_top_k: int
    plan_reason: str

    vector_context: Annotated[list[dict[str, Any]], operator.add]
    graph_context: Annotated[list[dict[str, Any]], operator.add]
    entity_ids: Annotated[list[str], operator.add]
    messages: Annotated[list[dict[str, Any]], operator.add]

    guardrails: dict[str, Any]
    answer: str
    confidence: float
    iteration: int
    final_reason: str
