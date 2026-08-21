"""Specialized agent nodes for the supply-chain LangGraph multi-agent graph."""
from __future__ import annotations

from typing import Any

from .state import SupplyChainAgentState


def triage_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Classify the question and produce a retrieval plan."""
    from domain import classify_request_type, select_retrieval_plan

    question = state["question"]
    entity_id = state.get("entity_id")
    request_type = classify_request_type(question, entity_id)
    plan = select_retrieval_plan(request_type, question, entity_id, 5)

    return {
        "request_type": request_type,
        "plan_query_text": plan.query_text,
        "plan_top_k": plan.top_k,
        "plan_reason": plan.reason,
        "messages": [{"agent": "triage", "action": "classify", "request_type": request_type, "reason": plan.reason}],
    }


def vector_retrieval_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Run vector similarity search against Qdrant."""
    from app import vector_context
    from domain import rank_vector_context

    query_text = state.get("plan_query_text", state["question"])
    entity_id = state.get("entity_id")
    top_k = state.get("plan_top_k", 5)
    request_type = state.get("request_type", "procurement_overview")

    raw = vector_context(query_text, entity_id, top_k)
    ranked = rank_vector_context(raw, request_type)

    entity_ids = list({item["entity_id"] for item in ranked if item.get("entity_id")})
    if entity_id and entity_id not in entity_ids:
        entity_ids.append(entity_id)

    return {
        "vector_context": ranked,
        "entity_ids": entity_ids,
        "messages": [{"agent": "vector_retrieval", "action": "search", "results_count": len(ranked)}],
    }


def graph_retrieval_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Query Neo4j supplier graph."""
    from app import graph_context
    from domain import rank_graph_context

    entity_ids = list(set(state.get("entity_ids", [])))
    request_type = state.get("request_type", "procurement_overview")

    if not entity_ids:
        return {"messages": [{"agent": "graph_retrieval", "action": "skip", "reason": "no entity IDs"}]}

    raw = graph_context(entity_ids)
    ranked = rank_graph_context(raw, request_type)

    return {
        "graph_context": ranked,
        "messages": [{"agent": "graph_retrieval", "action": "query", "results_count": len(ranked)}],
    }


def supplier_risk_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Analyze supplier risk signals from graph context."""
    graph_ctx = state.get("graph_context", [])
    risks: list[dict[str, Any]] = []
    for supplier in graph_ctx:
        sid = supplier.get("supplier_id", "unknown")
        signals = supplier.get("risk_signals", [])
        if signals:
            risks.append({"supplier_id": sid, "signal_count": len(signals), "risk_signals": signals})

    return {"messages": [{"agent": "supplier_risk", "action": "assess", "suppliers_with_risks": len(risks), "risks": risks}]}


def disruption_impact_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Assess disruption impact across the supply network."""
    graph_ctx = state.get("graph_context", [])
    impacts: list[dict[str, Any]] = []
    for supplier in graph_ctx:
        sid = supplier.get("supplier_id", "unknown")
        parts = supplier.get("parts", [])
        if parts:
            impacts.append({"supplier_id": sid, "affected_parts": len(parts), "parts": parts})

    return {"messages": [{"agent": "disruption_impact", "action": "analyze", "suppliers_affected": len(impacts), "impacts": impacts}]}


def quality_review_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Review quality signals from supplier graph."""
    graph_ctx = state.get("graph_context", [])
    reviews: list[dict[str, Any]] = []
    for supplier in graph_ctx:
        sid = supplier.get("supplier_id", "unknown")
        signals = [s for s in supplier.get("risk_signals", []) if s.get("signal") == "quality"]
        if signals:
            reviews.append({"supplier_id": sid, "quality_issues": len(signals)})

    return {"messages": [{"agent": "quality_review", "action": "review", "suppliers_reviewed": len(reviews)}]}


def confidence_evaluator(state: SupplyChainAgentState) -> dict[str, Any]:
    """Estimate retrieval confidence."""
    from domain.response_policy import estimate_confidence

    vector_ctx = state.get("vector_context", [])
    graph_ctx = state.get("graph_context", [])
    iteration = state.get("iteration", 0)
    confidence = estimate_confidence(vector_ctx, graph_ctx)

    return {
        "confidence": confidence,
        "iteration": iteration + 1,
        "messages": [{"agent": "confidence_evaluator", "action": "evaluate", "confidence": confidence}],
    }


def synthesis_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Generate the final answer."""
    from app import ask_ollama

    question = state["question"]
    vector_ctx = state.get("vector_context", [])
    graph_ctx = state.get("graph_context", [])
    answer = ask_ollama(question, vector_ctx, graph_ctx)

    return {"answer": answer, "final_reason": "synthesis_complete", "messages": [{"agent": "synthesis", "action": "generate", "answer_length": len(answer)}]}
