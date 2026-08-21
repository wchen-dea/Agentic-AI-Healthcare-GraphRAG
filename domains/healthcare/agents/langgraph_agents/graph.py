"""LangGraph graph definition for healthcare multi-agent orchestration.

Builds a ``StateGraph`` that wires triage → parallel retrieval → specialist
agents → confidence evaluation → synthesis, with conditional routing based
on ``request_type`` and a confidence-gated re-retrieval loop.

LangSmith tracing is automatically enabled when ``LANGSMITH_API_KEY`` and
``LANGSMITH_PROJECT`` environment variables are set.

MLflow tracing is automatically enabled when ``MLFLOW_TRACKING_URI`` is set.
"""
from __future__ import annotations

import os
from typing import Any

from langgraph.graph import END, StateGraph

from .agents import (
    coding_review_agent,
    confidence_evaluator,
    graph_retrieval_agent,
    lab_interpretation_agent,
    medication_safety_agent,
    synthesis_agent,
    triage_agent,
    vector_retrieval_agent,
)
from .mlflow_tracing import mlflow_enabled, trace_agent_node
from .state import HealthcareAgentState


# ── Conditional edge helpers ────────────────────────────────────────────────

def _route_specialist(state: HealthcareAgentState) -> str:
    """After retrieval, route to the appropriate specialist agent."""
    request_type = state.get("request_type", "patient_summary")
    if request_type == "medication_safety":
        return "medication_safety"
    if request_type == "lab_interpretation":
        return "lab_interpretation"
    if request_type == "coding_review":
        return "coding_review"
    return "confidence_evaluator"


def _should_continue(state: HealthcareAgentState) -> str:
    """After confidence evaluation, decide whether to synthesize or re-retrieve."""
    confidence = state.get("confidence", 0.0)
    iteration = state.get("iteration", 0)
    try:
        max_iterations = max(1, min(int(os.getenv("LANGGRAPH_MAX_ITERATIONS", "3")), 6))
    except (ValueError, TypeError):
        max_iterations = 3

    if confidence >= 0.75 or iteration >= max_iterations:
        return "synthesize"
    return "re_retrieve"


# ── Graph builder ──────────────────────────────────────────────────────────

def build_healthcare_graph() -> StateGraph:
    """Construct and compile the multi-agent healthcare LangGraph.

    Graph topology::

        ┌─────────┐
        │ triage  │
        └────┬────┘
             │
        ┌────▼──────────┐
        │ vector_search │
        └────┬──────────┘
             │
        ┌────▼──────────┐
        │ graph_lookup  │
        └────┬──────────┘
             │
        ┌────▼──────────────────┐
        │ route_specialist      │ ← conditional
        ├───────┬───────┬───────┤
        │med_saf│lab_int│cod_rev│ (or skip)
        └───┬───┴───┬───┴───┬───┘
            └───────┼───────┘
        ┌───────────▼───────────┐
        │ confidence_evaluator  │
        └───────────┬───────────┘
            ┌───────┴───────┐
            ▼               ▼
        synthesize     re-retrieve
            │          (back to vector)
        ┌───▼───┐
        │  END  │
        └───────┘
    """
    graph = StateGraph(HealthcareAgentState)

    # Wrap agent nodes with MLflow spans when tracing is active
    _triage = trace_agent_node("triage", triage_agent) if mlflow_enabled() else triage_agent
    _vector = trace_agent_node("vector_retrieval", vector_retrieval_agent) if mlflow_enabled() else vector_retrieval_agent
    _graph = trace_agent_node("graph_retrieval", graph_retrieval_agent) if mlflow_enabled() else graph_retrieval_agent
    _med = trace_agent_node("medication_safety", medication_safety_agent) if mlflow_enabled() else medication_safety_agent
    _lab = trace_agent_node("lab_interpretation", lab_interpretation_agent) if mlflow_enabled() else lab_interpretation_agent
    _coding = trace_agent_node("coding_review", coding_review_agent) if mlflow_enabled() else coding_review_agent
    _conf = trace_agent_node("confidence_evaluator", confidence_evaluator) if mlflow_enabled() else confidence_evaluator
    _synth = trace_agent_node("synthesis", synthesis_agent) if mlflow_enabled() else synthesis_agent

    graph.add_node("triage", _triage)
    graph.add_node("vector_retrieval", _vector)
    graph.add_node("graph_retrieval", _graph)
    graph.add_node("medication_safety", _med)
    graph.add_node("lab_interpretation", _lab)
    graph.add_node("coding_review", _coding)
    graph.add_node("confidence_evaluator", _conf)
    graph.add_node("synthesis", _synth)

    # Edges: linear pipeline until specialist routing
    graph.set_entry_point("triage")
    graph.add_edge("triage", "vector_retrieval")
    graph.add_edge("vector_retrieval", "graph_retrieval")

    # Conditional: specialist or straight to confidence
    graph.add_conditional_edges(
        "graph_retrieval",
        _route_specialist,
        {
            "medication_safety": "medication_safety",
            "lab_interpretation": "lab_interpretation",
            "coding_review": "coding_review",
            "confidence_evaluator": "confidence_evaluator",
        },
    )

    # Specialist agents converge to confidence evaluator
    graph.add_edge("medication_safety", "confidence_evaluator")
    graph.add_edge("lab_interpretation", "confidence_evaluator")
    graph.add_edge("coding_review", "confidence_evaluator")

    # Confidence gate: synthesize or loop back
    graph.add_conditional_edges(
        "confidence_evaluator",
        _should_continue,
        {
            "synthesize": "synthesis",
            "re_retrieve": "vector_retrieval",
        },
    )

    graph.add_edge("synthesis", END)

    return graph.compile()


# ── Public runner ──────────────────────────────────────────────────────────

def run_langgraph_query(
    question: str,
    patient_id: str | None = None,
) -> dict[str, Any]:
    """Execute the healthcare multi-agent graph and return a response dict
    compatible with the existing ``run_query`` output shape.

    When ``LANGSMITH_API_KEY`` is set, every invocation is automatically
    traced and visible in the LangSmith dashboard.

    When ``MLFLOW_TRACKING_URI`` is set, the full pipeline is traced as
    an MLflow span hierarchy visible in the MLflow Tracing UI.
    """
    from .mlflow_tracing import trace_query

    def _invoke(q, pid):
        return _run_langgraph_pipeline(q, pid)

    if mlflow_enabled():
        return trace_query(question, patient_id, "langgraph", _invoke)
    return _run_langgraph_pipeline(question, patient_id)


def _run_langgraph_pipeline(
    question: str,
    patient_id: str | None = None,
) -> dict[str, Any]:
    """Inner pipeline — separated so MLflow can wrap the full execution."""
    compiled_graph = build_healthcare_graph()

    initial_state: HealthcareAgentState = {
        "question": question,
        "patient_id": patient_id,
        "vector_context": [],
        "graph_context": [],
        "patient_ids": [],
        "messages": [],
        "confidence": 0.0,
        "iteration": 0,
    }

    # LangSmith config (auto-enabled via env vars)
    config: dict[str, Any] = {}
    langsmith_project = os.getenv("LANGSMITH_PROJECT", "healthcare-graphrag")
    if os.getenv("LANGSMITH_API_KEY"):
        config["callbacks"] = []  # LangSmith auto-instruments via env
        config["metadata"] = {
            "project": langsmith_project,
            "patient_id": patient_id or "none",
        }

    final_state = compiled_graph.invoke(initial_state, config=config)

    # Deduplicate patient_ids that may have been appended from multiple iterations
    patient_ids = sorted(set(final_state.get("patient_ids", [])))

    return {
        "question": question,
        "request_type": final_state.get("request_type", "patient_summary"),
        "retrieval_plan": {
            "name": final_state.get("request_type", "patient_summary"),
            "top_k": final_state.get("plan_top_k", 5),
            "reason": final_state.get("plan_reason", "LangGraph agent plan"),
        },
        "patients": patient_ids,
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
