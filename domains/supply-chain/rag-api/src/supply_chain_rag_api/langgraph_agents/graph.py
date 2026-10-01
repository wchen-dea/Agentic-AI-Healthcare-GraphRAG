"""LangGraph graph definition for supply-chain multi-agent orchestration."""
from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, StateGraph

from .agents import (
    confidence_evaluator,
    disruption_impact_agent,
    graph_retrieval_agent,
    quality_review_agent,
    supplier_risk_agent,
    synthesis_agent,
    triage_agent,
    vector_retrieval_agent,
)
from .mlflow_tracing import mlflow_enabled, trace_agent_node
from .state import SupplyChainAgentState


def _route_specialist(state: SupplyChainAgentState) -> str:
    request_type = state.get("request_type", "procurement_overview")
    if request_type == "supplier_risk":
        return "supplier_risk"
    if request_type == "disruption_impact":
        return "disruption_impact"
    if request_type == "quality_review":
        return "quality_review"
    return "confidence_evaluator"


def _should_continue(state: SupplyChainAgentState) -> str:
    confidence = state.get("confidence", 0.0)
    iteration = state.get("iteration", 0)
    try:
        max_iterations = max(1, min(int(os.getenv("LANGGRAPH_MAX_ITERATIONS", "3")), 6))
    except (ValueError, TypeError):
        max_iterations = 3

    if confidence >= 0.75 or iteration >= max_iterations:
        return "synthesize"
    return "re_retrieve"


def build_supply_chain_graph() -> StateGraph:
    graph = StateGraph(SupplyChainAgentState)

    _triage = trace_agent_node("triage", triage_agent) if mlflow_enabled() else triage_agent
    _vector = trace_agent_node("vector_retrieval", vector_retrieval_agent) if mlflow_enabled() else vector_retrieval_agent
    _graph = trace_agent_node("graph_retrieval", graph_retrieval_agent) if mlflow_enabled() else graph_retrieval_agent
    _risk = trace_agent_node("supplier_risk", supplier_risk_agent) if mlflow_enabled() else supplier_risk_agent
    _disruption = trace_agent_node("disruption_impact", disruption_impact_agent) if mlflow_enabled() else disruption_impact_agent
    _quality = trace_agent_node("quality_review", quality_review_agent) if mlflow_enabled() else quality_review_agent
    _conf = trace_agent_node("confidence_evaluator", confidence_evaluator) if mlflow_enabled() else confidence_evaluator
    _synth = trace_agent_node("synthesis", synthesis_agent) if mlflow_enabled() else synthesis_agent

    graph.add_node("triage", _triage)
    graph.add_node("vector_retrieval", _vector)
    graph.add_node("graph_retrieval", _graph)
    graph.add_node("supplier_risk", _risk)
    graph.add_node("disruption_impact", _disruption)
    graph.add_node("quality_review", _quality)
    graph.add_node("confidence_evaluator", _conf)
    graph.add_node("synthesis", _synth)

    graph.set_entry_point("triage")
    graph.add_edge("triage", "vector_retrieval")
    graph.add_edge("vector_retrieval", "graph_retrieval")

    graph.add_conditional_edges(
        "graph_retrieval",
        _route_specialist,
        {
            "supplier_risk": "supplier_risk",
            "disruption_impact": "disruption_impact",
            "quality_review": "quality_review",
            "confidence_evaluator": "confidence_evaluator",
        },
    )

    graph.add_edge("supplier_risk", "confidence_evaluator")
    graph.add_edge("disruption_impact", "confidence_evaluator")
    graph.add_edge("quality_review", "confidence_evaluator")

    graph.add_conditional_edges(
        "confidence_evaluator",
        _should_continue,
        {"synthesize": "synthesis", "re_retrieve": "vector_retrieval"},
    )

    graph.add_edge("synthesis", END)

    return graph.compile()


def run_langgraph_query(
    question: str,
    entity_id: str | None = None,
) -> dict[str, Any]:
    from .mlflow_tracing import trace_query

    def _invoke(q, eid):
        return _run_pipeline(q, eid)

    if mlflow_enabled():
        return trace_query(question, entity_id, "langgraph", _invoke)
    return _run_pipeline(question, entity_id)


def _run_pipeline(question: str, entity_id: str | None = None) -> dict[str, Any]:
    compiled_graph = build_supply_chain_graph()

    initial_state: SupplyChainAgentState = {
        "question": question,
        "entity_id": entity_id,
        "vector_context": [],
        "graph_context": [],
        "entity_ids": [],
        "messages": [],
        "confidence": 0.0,
        "iteration": 0,
    }

    config: dict[str, Any] = {}
    if os.getenv("LANGSMITH_API_KEY"):
        config["metadata"] = {"project": os.getenv("LANGSMITH_PROJECT", "supplychain-graphrag"), "entity_id": entity_id or "none"}

    final_state = compiled_graph.invoke(initial_state, config=config)
    entity_ids = sorted(set(final_state.get("entity_ids", [])))

    return {
        "question": question,
        "request_type": final_state.get("request_type", "procurement_overview"),
        "retrieval_plan": {
            "name": final_state.get("request_type", "procurement_overview"),
            "top_k": final_state.get("plan_top_k", 5),
            "reason": final_state.get("plan_reason", "LangGraph agent plan"),
        },
        "entities": entity_ids,
        "vector_context": final_state.get("vector_context", []),
        "graph_context": final_state.get("graph_context", []),
        "answer": final_state.get("answer", ""),
        "langgraph": {
            "enabled": True,
            "iterations": final_state.get("iteration", 0),
            "final_reason": final_state.get("final_reason", "unknown"),
            "confidence": final_state.get("confidence", 0.0),
            "agent_trace": final_state.get("messages", []),
        },
    }
