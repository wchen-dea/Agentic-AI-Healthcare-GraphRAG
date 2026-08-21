"""LangSmith tracing and evaluation integration for healthcare LangGraph agents.

Provides:
- Automatic tracing via environment variables (LANGSMITH_API_KEY, LANGSMITH_PROJECT)
- Evaluation datasets and scoring for comparing single-pass vs ReAct vs LangGraph
- Custom healthcare-specific evaluators
"""
from __future__ import annotations

import os
from typing import Any


def get_langsmith_config(
    *,
    run_name: str | None = None,
    patient_id: str | None = None,
    mode: str = "langgraph",
) -> dict[str, Any]:
    """Build a LangSmith-compatible config dict for graph invocation.

    Tracing activates automatically when ``LANGSMITH_API_KEY`` is set.
    """
    config: dict[str, Any] = {
        "metadata": {
            "mode": mode,
            "patient_id": patient_id or "none",
        },
    }
    if run_name:
        config["run_name"] = run_name
    return config


def langsmith_enabled() -> bool:
    return bool(os.getenv("LANGSMITH_API_KEY"))


# ── Evaluation helpers ─────────────────────────────────────────────────────

EVALUATION_DATASET = [
    {
        "question": "What medications is patient P-001 currently taking and are there any interactions?",
        "patient_id": "P-001",
        "expected_type": "medication_safety",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval", "medication_safety"],
    },
    {
        "question": "Show me the latest lab results for patient P-002",
        "patient_id": "P-002",
        "expected_type": "lab_interpretation",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval", "lab_interpretation"],
    },
    {
        "question": "What is the clinical summary for patient P-003?",
        "patient_id": "P-003",
        "expected_type": "patient_summary",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval"],
    },
    {
        "question": "Are there any coding gaps in the claims for patient P-004?",
        "patient_id": "P-004",
        "expected_type": "coding_review",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval", "coding_review"],
    },
    {
        "question": "Which patients across the cohort have the highest risk of deterioration?",
        "patient_id": None,
        "expected_type": "cohort_triage",
        "expected_agents": ["triage", "vector_retrieval", "graph_retrieval"],
    },
]


def evaluate_routing_accuracy(trace_messages: list[dict[str, Any]], expected_type: str) -> dict[str, Any]:
    """Score whether the triage agent routed to the correct request type."""
    triage_msg = next((m for m in trace_messages if m.get("agent") == "triage"), None)
    actual_type = triage_msg.get("request_type") if triage_msg else None
    return {
        "metric": "routing_accuracy",
        "expected": expected_type,
        "actual": actual_type,
        "score": 1.0 if actual_type == expected_type else 0.0,
    }


def evaluate_agent_coverage(
    trace_messages: list[dict[str, Any]], expected_agents: list[str],
) -> dict[str, Any]:
    """Score whether all expected specialist agents were activated."""
    actual_agents = [m.get("agent") for m in trace_messages if m.get("agent")]
    covered = sum(1 for a in expected_agents if a in actual_agents)
    return {
        "metric": "agent_coverage",
        "expected_agents": expected_agents,
        "actual_agents": actual_agents,
        "score": covered / len(expected_agents) if expected_agents else 0.0,
    }


def evaluate_evidence_completeness(result: dict[str, Any]) -> dict[str, Any]:
    """Score whether both vector and graph evidence channels contributed."""
    has_vector = bool(result.get("vector_context"))
    has_graph = bool(result.get("graph_context"))
    if has_vector and has_graph:
        score = 1.0
    elif has_vector or has_graph:
        score = 0.5
    else:
        score = 0.0
    return {
        "metric": "evidence_completeness",
        "has_vector": has_vector,
        "has_graph": has_graph,
        "score": score,
    }


def evaluate_answer_quality(result: dict[str, Any]) -> dict[str, Any]:
    """Basic answer quality heuristics (non-empty, no error prefix, reasonable length)."""
    answer = result.get("answer", "")
    has_answer = bool(answer.strip())
    is_error = answer.startswith("LLM error:")
    reasonable_length = 50 < len(answer) < 5000

    score = 0.0
    if has_answer and not is_error:
        score = 0.5
        if reasonable_length:
            score = 1.0

    return {
        "metric": "answer_quality",
        "has_answer": has_answer,
        "is_error": is_error,
        "answer_length": len(answer),
        "score": score,
    }


def run_evaluation_suite(
    query_fn, mode: str = "langgraph",
) -> list[dict[str, Any]]:
    """Run the evaluation dataset through a query function and score results.

    ``query_fn`` should accept ``(question, patient_id)`` and return a result
    dict with ``vector_context``, ``graph_context``, ``answer``, and
    optionally ``langgraph.agent_trace`` or ``react.actions``.
    """
    results: list[dict[str, Any]] = []
    for case in EVALUATION_DATASET:
        result = query_fn(case["question"], case.get("patient_id"))

        trace = []
        if "langgraph" in result:
            trace = result["langgraph"].get("agent_trace", [])
        elif "react" in result:
            trace = result["react"].get("actions", [])

        scores = {
            "case": case["question"][:60],
            "mode": mode,
            "routing": evaluate_routing_accuracy(trace, case["expected_type"]),
            "agent_coverage": evaluate_agent_coverage(trace, case["expected_agents"]),
            "evidence": evaluate_evidence_completeness(result),
            "answer_quality": evaluate_answer_quality(result),
        }
        results.append(scores)

    return results
