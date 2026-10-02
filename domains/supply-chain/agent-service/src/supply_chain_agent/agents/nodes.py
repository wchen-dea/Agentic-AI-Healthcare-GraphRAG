"""Specialist agent nodes for the supply-chain LangGraph multi-agent graph.

Nodes reach data stores and the LLM only through the runtime port
(``orchestration.runtime``), never through the composition root.
"""
from __future__ import annotations

from typing import Any

from supply_chain_agent.orchestration.planner import classify_request_type, select_retrieval_plan
from supply_chain_agent.orchestration.runtime import get_runtime
from supply_chain_agent.orchestration.state import SupplyChainAgentState
from supply_chain_agent.retrieval.evidence import rank_graph_context, rank_vector_context
from supply_chain_agent.safety.guardrails import classify_input, classify_output
from supply_chain_agent.safety.response_policy import estimate_confidence

DEFAULT_CONTEXT_LIMIT = 5


# ── Guardrail nodes (deterministic policy; run before and after agents) ────

def input_guardrail(state: SupplyChainAgentState) -> dict[str, Any]:
    """Block prompt injection and sensitive identifiers before any tool executes."""
    check = classify_input(state["question"])
    if check.passed:
        return {
            "guardrails": {"input_blocked": False},
            "messages": [{"agent": "input_guardrail", "action": "pass"}],
        }
    return {
        "guardrails": {"input_blocked": True, "category": check.category},
        "answer": f"Request blocked: {check.category} — {', '.join(check.reasons)}",
        "final_reason": "input_blocked",
        "messages": [{"agent": "input_guardrail", "action": "block", "reason": check.category}],
    }


def output_guardrail(state: SupplyChainAgentState) -> dict[str, Any]:
    """Withhold unsafe generated answers before they leave the orchestrator."""
    check = classify_output(state.get("answer", ""))
    guardrails = dict(state.get("guardrails") or {})
    if check.passed:
        guardrails["output_blocked"] = False
        return {"guardrails": guardrails, "messages": [{"agent": "output_guardrail", "action": "pass"}]}
    guardrails.update({"output_blocked": True, "category": check.category})
    return {
        "guardrails": guardrails,
        "answer": "Response withheld due to safety review.",
        "final_reason": "output_blocked",
        "messages": [{"agent": "output_guardrail", "action": "block", "reason": check.category}],
    }


# ── Planning and retrieval ──────────────────────────────────────────────────

def triage_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Classify the question and produce a retrieval plan."""
    question = state["question"]
    entity_id = state.get("entity_id")
    request_type = classify_request_type(question, entity_id)
    plan = select_retrieval_plan(
        request_type, question, entity_id, state.get("context_limit", DEFAULT_CONTEXT_LIMIT)
    )
    return {
        "request_type": request_type,
        "plan_query_text": plan.query_text,
        "plan_top_k": plan.top_k,
        "plan_reason": plan.reason,
        "messages": [{"agent": "triage", "action": "classify", "request_type": request_type, "reason": plan.reason}],
    }


def vector_retrieval_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Run vector similarity search through the runtime port."""
    entity_id = state.get("entity_id")
    raw = get_runtime().vector_search(
        state.get("plan_query_text", state["question"]), entity_id, state.get("plan_top_k", DEFAULT_CONTEXT_LIMIT)
    )
    ranked = rank_vector_context(raw, state.get("request_type", "procurement_overview"))

    entity_ids = list(dict.fromkeys(item["entity_id"] for item in ranked if item.get("entity_id")))
    if entity_id and entity_id not in entity_ids:
        entity_ids.append(entity_id)

    return {
        "vector_context": ranked,
        "entity_ids": entity_ids,
        "messages": [{"agent": "vector_retrieval", "action": "search", "results_count": len(ranked)}],
    }


def graph_retrieval_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Query the supplier graph through the runtime port."""
    entity_ids = sorted(set(state.get("entity_ids", [])))
    if not entity_ids:
        return {"messages": [{"agent": "graph_retrieval", "action": "skip", "reason": "no entity IDs"}]}

    ranked = rank_graph_context(get_runtime().graph_search(entity_ids), state.get("request_type", "procurement_overview"))
    return {
        "graph_context": ranked,
        "messages": [{"agent": "graph_retrieval", "action": "query", "results_count": len(ranked)}],
    }


# ── Specialists (read the canonical graph keys from retrieval.search) ───────

def supplier_risk_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Summarize risk signals per entity."""
    risks = [
        {
            "entity_id": entity.get("entity_id", "unknown"),
            "risk_score": entity.get("risk_score"),
            "signal_count": len(entity.get("risk_signals") or []),
            "categories": sorted({s.get("category") for s in entity.get("risk_signals") or [] if s.get("category")}),
        }
        for entity in state.get("graph_context", [])
        if entity.get("risk_signals")
    ]
    return {"messages": [{"agent": "supplier_risk", "action": "assess", "entities_with_risks": len(risks), "risks": risks}]}


def disruption_impact_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Relate active disruptions to the parts each entity supplies."""
    impacts = [
        {
            "entity_id": entity.get("entity_id", "unknown"),
            "disruptions": len(entity.get("disruptions") or []),
            "affected_parts": [p.get("part_id") for p in entity.get("supplied_parts") or [] if p.get("part_id")],
        }
        for entity in state.get("graph_context", [])
        if entity.get("disruptions")
    ]
    return {
        "messages": [{"agent": "disruption_impact", "action": "analyze", "entities_affected": len(impacts), "impacts": impacts}]
    }


def quality_review_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Count failed quality inspections per entity."""
    reviews = []
    for entity in state.get("graph_context", []):
        failed = [q for q in entity.get("quality_inspections") or [] if str(q.get("result", "")).lower() != "pass"]
        if failed:
            reviews.append({"entity_id": entity.get("entity_id", "unknown"), "quality_issues": len(failed)})
    return {"messages": [{"agent": "quality_review", "action": "review", "entities_reviewed": len(reviews), "reviews": reviews}]}


def inventory_planning_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Flag parts held below their reorder point."""
    below = [
        {"entity_id": entity.get("entity_id", "unknown"), "part_id": item.get("part_id"), "days_of_supply": item.get("days_of_supply")}
        for entity in state.get("graph_context", [])
        for item in entity.get("inventory") or []
        if item.get("below_reorder")
    ]
    return {"messages": [{"agent": "inventory_planning", "action": "check_reorder", "below_reorder": len(below), "items": below}]}


# ── Evaluation and synthesis ────────────────────────────────────────────────

def confidence_evaluator(state: SupplyChainAgentState) -> dict[str, Any]:
    """Estimate retrieval confidence."""
    confidence = estimate_confidence(state.get("vector_context", []), state.get("graph_context", []))
    return {
        "confidence": confidence,
        "iteration": state.get("iteration", 0) + 1,
        "messages": [{"agent": "confidence_evaluator", "action": "evaluate", "confidence": confidence}],
    }


def synthesis_agent(state: SupplyChainAgentState) -> dict[str, Any]:
    """Generate the final answer through the runtime port."""
    answer = get_runtime().synthesize(
        state["question"], state.get("vector_context", []), state.get("graph_context", [])
    )
    return {
        "answer": answer,
        "final_reason": "synthesis_complete",
        "messages": [{"agent": "synthesis", "action": "generate", "answer_length": len(answer)}],
    }
