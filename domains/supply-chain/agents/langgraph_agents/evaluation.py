"""Evaluation dataset and scoring for supply-chain agents."""
from __future__ import annotations

import os
from typing import Any


EVALUATION_DATASET = [
    {
        "question": "Is this supplier a single-source risk for critical parts?",
        "entity_id": "SUP-001",
        "expected_type": "supplier_risk",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval", "supplier_risk"],
    },
    {
        "question": "Where is the delayed shipment for PO-2024-001?",
        "entity_id": "SUP-002",
        "expected_type": "shipment_tracking",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval"],
    },
    {
        "question": "What is the defect rate trend for this supplier?",
        "entity_id": "SUP-003",
        "expected_type": "quality_review",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval", "quality_review"],
    },
    {
        "question": "What is the cascade impact of the factory shutdown?",
        "entity_id": None,
        "expected_type": "disruption_impact",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval", "disruption_impact"],
    },
    {
        "question": "Which parts are below reorder point?",
        "entity_id": None,
        "expected_type": "inventory_planning",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval"],
    },
]


def evaluate_routing_accuracy(trace_messages: list[dict[str, Any]], expected_type: str) -> dict[str, Any]:
    triage_msg = next((m for m in trace_messages if m.get("agent") == "triage"), None)
    actual_type = triage_msg.get("request_type") if triage_msg else None
    return {"metric": "routing_accuracy", "expected": expected_type, "actual": actual_type, "score": 1.0 if actual_type == expected_type else 0.0}


def evaluate_agent_coverage(trace_messages: list[dict[str, Any]], expected_agents: list[str]) -> dict[str, Any]:
    actual_agents = [m.get("agent") for m in trace_messages if m.get("agent")]
    covered = sum(1 for a in expected_agents if a in actual_agents)
    return {"metric": "agent_coverage", "expected_agents": expected_agents, "actual_agents": actual_agents, "score": covered / len(expected_agents) if expected_agents else 0.0}


def evaluate_evidence_completeness(result: dict[str, Any]) -> dict[str, Any]:
    has_vector = bool(result.get("vector_context"))
    has_graph = bool(result.get("graph_context"))
    score = 1.0 if (has_vector and has_graph) else (0.5 if (has_vector or has_graph) else 0.0)
    return {"metric": "evidence_completeness", "has_vector": has_vector, "has_graph": has_graph, "score": score}


def evaluate_answer_quality(result: dict[str, Any]) -> dict[str, Any]:
    answer = result.get("answer", "")
    has_answer = bool(answer.strip())
    is_error = answer.startswith("LLM error:")
    reasonable_length = 50 < len(answer) < 5000
    score = 0.0
    if has_answer and not is_error:
        score = 1.0 if reasonable_length else 0.5
    return {"metric": "answer_quality", "has_answer": has_answer, "is_error": is_error, "answer_length": len(answer), "score": score}
