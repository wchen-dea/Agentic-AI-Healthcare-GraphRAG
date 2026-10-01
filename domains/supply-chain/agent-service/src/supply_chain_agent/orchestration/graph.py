"""LangGraph definition for supply-chain multi-agent orchestration.

Topology::

    input_guardrail ─ blocked ─► END
          │ allowed
    triage → vector_retrieval → graph_retrieval → [specialist] → confidence_evaluator
                   ▲                                                   │
                   └──────────────── re_retrieve ◄─────────────────────┤
                                                                       ▼ synthesize
                                                  synthesis → output_guardrail → END
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, StateGraph

from supply_chain_agent.agents.nodes import (
    DEFAULT_CONTEXT_LIMIT,
    confidence_evaluator,
    disruption_impact_agent,
    graph_retrieval_agent,
    input_guardrail,
    inventory_planning_agent,
    output_guardrail,
    quality_review_agent,
    supplier_risk_agent,
    synthesis_agent,
    triage_agent,
    vector_retrieval_agent,
)
from supply_chain_agent.observability.tracing import mlflow_enabled, trace_agent_node, trace_query
from supply_chain_agent.orchestration.state import SupplyChainAgentState

_SPECIALISTS = {
    "supplier_risk": supplier_risk_agent,
    "disruption_impact": disruption_impact_agent,
    "quality_review": quality_review_agent,
    "inventory_planning": inventory_planning_agent,
}


def _route_specialist(state: SupplyChainAgentState) -> str:
    request_type = state.get("request_type", "procurement_overview")
    return request_type if request_type in _SPECIALISTS else "confidence_evaluator"


def _should_continue(state: SupplyChainAgentState) -> str:
    try:
        max_iterations = max(1, min(int(os.getenv("LANGGRAPH_MAX_ITERATIONS", "3")), 6))
    except (ValueError, TypeError):
        max_iterations = 3
    if state.get("confidence", 0.0) >= 0.75 or state.get("iteration", 0) >= max_iterations:
        return "synthesize"
    return "re_retrieve"


def _after_input_guardrail(state: SupplyChainAgentState) -> str:
    return "blocked" if (state.get("guardrails") or {}).get("input_blocked") else "allowed"


def build_supply_chain_graph():
    traced = mlflow_enabled()
    graph = StateGraph(SupplyChainAgentState)

    nodes = {
        "input_guardrail": input_guardrail,
        "triage": triage_agent,
        "vector_retrieval": vector_retrieval_agent,
        "graph_retrieval": graph_retrieval_agent,
        **_SPECIALISTS,
        "confidence_evaluator": confidence_evaluator,
        "synthesis": synthesis_agent,
        "output_guardrail": output_guardrail,
    }
    for name, fn in nodes.items():
        graph.add_node(name, trace_agent_node(name, fn) if traced else fn)

    graph.set_entry_point("input_guardrail")
    graph.add_conditional_edges("input_guardrail", _after_input_guardrail, {"allowed": "triage", "blocked": END})
    graph.add_edge("triage", "vector_retrieval")
    graph.add_edge("vector_retrieval", "graph_retrieval")
    graph.add_conditional_edges(
        "graph_retrieval",
        _route_specialist,
        {**{name: name for name in _SPECIALISTS}, "confidence_evaluator": "confidence_evaluator"},
    )
    for name in _SPECIALISTS:
        graph.add_edge(name, "confidence_evaluator")
    graph.add_conditional_edges(
        "confidence_evaluator", _should_continue, {"synthesize": "synthesis", "re_retrieve": "vector_retrieval"}
    )
    graph.add_edge("synthesis", "output_guardrail")
    graph.add_edge("output_guardrail", END)
    return graph.compile()


def run_langgraph_query(
    question: str, entity_id: str | None = None, *, context_limit: int = DEFAULT_CONTEXT_LIMIT
) -> dict[str, Any]:
    if mlflow_enabled():
        return trace_query(
            question, entity_id, "langgraph", lambda q, eid: _run_pipeline(q, eid, context_limit=context_limit)
        )
    return _run_pipeline(question, entity_id, context_limit=context_limit)


def _run_pipeline(question: str, entity_id: str | None, *, context_limit: int) -> dict[str, Any]:
    initial_state: SupplyChainAgentState = {
        "question": question,
        "entity_id": entity_id,
        "context_limit": context_limit,
        "vector_context": [],
        "graph_context": [],
        "entity_ids": [],
        "messages": [],
        "guardrails": {},
        "confidence": 0.0,
        "iteration": 0,
    }

    config: dict[str, Any] = {}
    if os.getenv("LANGSMITH_API_KEY"):
        config["metadata"] = {
            "project": os.getenv("LANGSMITH_PROJECT", "supplychain-graphrag"),
            "entity_id": entity_id or "none",
        }

    final_state = build_supply_chain_graph().invoke(initial_state, config=config)
    request_type = final_state.get("request_type", "procurement_overview")
    return {
        "question": question,
        "request_type": request_type,
        "retrieval_plan": {
            "name": request_type,
            "top_k": final_state.get("plan_top_k", context_limit),
            "reason": final_state.get("plan_reason", "LangGraph agent plan"),
        },
        "entities": sorted(set(final_state.get("entity_ids", []))),
        "vector_context": final_state.get("vector_context", []),
        "graph_context": final_state.get("graph_context", []),
        "answer": final_state.get("answer", ""),
        "confidence": final_state.get("confidence", 0.0),
        "guardrails": dict(final_state.get("guardrails") or {}),
        "langgraph": {
            "enabled": True,
            "iterations": final_state.get("iteration", 0),
            "final_reason": final_state.get("final_reason", "unknown"),
            "confidence": final_state.get("confidence", 0.0),
            "agent_trace": final_state.get("messages", []),
        },
    }
