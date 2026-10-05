"""LangGraph graph definition for healthcare multi-agent orchestration.

Builds a ``StateGraph`` that wires triage → parallel retrieval → specialist
agents → confidence evaluation → synthesis, with conditional routing based
on ``request_type`` and a confidence-gated re-retrieval loop.

MLflow tracing is automatically enabled when ``MLFLOW_TRACKING_URI`` is set.

When ``HITL_ENABLED`` is set, a ``human_review`` node pauses the run before
synthesis for clinician approval (see ``orchestration.hitl``). Compiled graphs
are cached per (tracing, HITL) configuration; call ``clear_graph_cache`` after
changing those settings at runtime.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from langgraph.graph import END, StateGraph

from healthcare_agent.agents.nodes import (
    coding_review_agent,
    confidence_evaluator,
    graph_retrieval_agent,
    input_guardrail,
    lab_interpretation_agent,
    medication_safety_agent,
    output_guardrail,
    synthesis_agent,
    triage_agent,
    vector_retrieval_agent,
)
from healthcare_agent.agents.registry import resolve_delegation
from healthcare_agent.observability.tracing import mlflow_enabled, trace_agent_node
from healthcare_agent.orchestration.hitl import (
    PENDING_ANSWER,
    after_human_review,
    get_checkpointer,
    hitl_enabled,
    human_review,
)
from healthcare_agent.orchestration.memory import PatientMemoryRecord
from healthcare_agent.orchestration.state import HealthcareAgentState

DEFAULT_CONTEXT_LIMIT = 5


# ── Delegation router ───────────────────────────────────────────────────────

_DELEGATION_HANDLERS = {
    "lab_interpretation": lab_interpretation_agent,
    "medication_safety": medication_safety_agent,
    "coding_review": coding_review_agent,
}


def delegation_router(state: HealthcareAgentState) -> dict[str, Any]:
    """Resolve pending delegation requests by invoking target agents."""
    pending = state.get("delegation_requests", [])
    resolved_ids = {
        (r.get("from_agent"), r.get("capability"))
        for r in state.get("delegation_responses", [])
    }

    new_responses: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []

    for req in pending:
        already_resolved = (req.get("from_agent"), req.get("capability")) in resolved_ids
        if already_resolved:
            continue

        target = resolve_delegation(type("R", (), req)()) if isinstance(req, dict) else None
        if target is None:
            target = req.get("to_agent")

        handler = _DELEGATION_HANDLERS.get(target)
        if handler:
            sub_result = handler(state)
            for resp in sub_result.get("delegation_responses", []):
                new_responses.append(resp)
            messages.append({
                "agent": "delegation_router",
                "action": "resolve",
                "from_agent": req.get("from_agent"),
                "to_agent": target,
                "capability": req.get("capability"),
            })

    result: dict[str, Any] = {"messages": messages}
    if new_responses:
        result["delegation_responses"] = new_responses
    return result


def _has_pending_delegations(state: HealthcareAgentState) -> str:
    """Check if there are unresolved delegation requests after specialist."""
    pending = state.get("delegation_requests", [])
    resolved = {
        (r.get("from_agent"), r.get("capability"))
        for r in state.get("delegation_responses", [])
    }
    unresolved = [
        req for req in pending
        if (req.get("from_agent"), req.get("capability")) not in resolved
    ]
    return "delegate" if unresolved else "evaluate"


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


def _max_iterations() -> int:
    try:
        return max(1, min(int(os.getenv("LANGGRAPH_MAX_ITERATIONS", "3")), 6))
    except (ValueError, TypeError):
        return 3


# Supersteps per iteration: retrieval, graph, specialist, delegation hops,
# confidence. Generous headroom; this is a hard backstop, not the loop policy.
_STEPS_PER_ITERATION = 10
_STEP_OVERHEAD = 10


def _recursion_limit() -> int:
    return _max_iterations() * _STEPS_PER_ITERATION + _STEP_OVERHEAD


def _should_continue(state: HealthcareAgentState) -> str:
    """After confidence evaluation, decide whether to synthesize or re-retrieve."""
    confidence = state.get("confidence", 0.0)
    iteration = state.get("iteration", 0)

    if confidence >= 0.75 or iteration >= _max_iterations():
        return "synthesize"
    return "re_retrieve"


def _after_input_guardrail(state: HealthcareAgentState) -> str:
    return "blocked" if (state.get("guardrails") or {}).get("input_blocked") else "allowed"


def patient_memory_retrieval(state: HealthcareAgentState) -> dict[str, Any]:
    """Load governed patient facts into a separate trusted context channel."""
    record = state.get("_patient_memory_record")
    if not isinstance(record, PatientMemoryRecord):
        return {
            "patient_memory_context": [],
            "patient_memory_facts": [],
            "patient_memory_policy": {},
            "patient_memory_metadata": {"loaded": False},
        }
    facts = record.active_facts()
    return {
        "patient_memory_context": record.to_context(),
        "patient_memory_facts": [fact.to_dict() for fact in facts],
        "patient_memory_policy": {
            "consent_required": record.policy.consent_required,
            "consent_granted": record.policy.consent_granted,
            "retention_seconds": record.policy.retention_seconds,
            "max_facts": record.policy.max_facts,
        },
        "patient_memory_metadata": {
            "loaded": True,
            "patient_id": record.patient_id,
            "fact_count": len(facts),
        },
    }


# ── Graph builder ──────────────────────────────────────────────────────────

def build_healthcare_graph(*, with_hitl: bool | None = None) -> Any:
    """Construct and compile the multi-agent healthcare LangGraph.

    ``with_hitl`` defaults to ``hitl_enabled()``. When true, a ``human_review``
    node sits between the confidence gate and synthesis and the graph is
    compiled with a checkpointer so interrupted runs can be resumed.

    Graph topology::

        ┌─────────────────┐
        │ input_guardrail │ ── blocked ──► END
        └────┬────────────┘
             │
        ┌────▼────┐
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
       [human_review]  ← HITL only; reject ──► output_guardrail
            │
        ┌───▼──────────────┐
        │ output_guardrail │
        └───┬──────────────┘
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
    _delegate = trace_agent_node("delegation_router", delegation_router) if mlflow_enabled() else delegation_router

    graph.add_node("input_guardrail", input_guardrail)
    graph.add_node("output_guardrail", output_guardrail)

    graph.add_node("triage", _triage)
    graph.add_node("patient_memory_retrieval", patient_memory_retrieval)
    graph.add_node("vector_retrieval", _vector)
    graph.add_node("graph_retrieval", _graph)
    graph.add_node("medication_safety", _med)
    graph.add_node("lab_interpretation", _lab)
    graph.add_node("coding_review", _coding)
    graph.add_node("delegation_router", _delegate)
    graph.add_node("confidence_evaluator", _conf)
    graph.add_node("synthesis", _synth)

    # Edges: linear pipeline until specialist routing
    graph.set_entry_point("input_guardrail")
    graph.add_conditional_edges(
        "input_guardrail",
        _after_input_guardrail,
        {"blocked": END, "allowed": "triage"},
    )
    graph.add_edge("triage", "patient_memory_retrieval")
    graph.add_edge("patient_memory_retrieval", "vector_retrieval")
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

    # Specialist agents check for delegations before confidence
    graph.add_conditional_edges(
        "medication_safety",
        _has_pending_delegations,
        {"delegate": "delegation_router", "evaluate": "confidence_evaluator"},
    )
    graph.add_conditional_edges(
        "lab_interpretation",
        _has_pending_delegations,
        {"delegate": "delegation_router", "evaluate": "confidence_evaluator"},
    )
    graph.add_conditional_edges(
        "coding_review",
        _has_pending_delegations,
        {"delegate": "delegation_router", "evaluate": "confidence_evaluator"},
    )

    # Delegation router feeds back to confidence after resolving
    graph.add_edge("delegation_router", "confidence_evaluator")

    if with_hitl is None:
        with_hitl = hitl_enabled()

    # Confidence gate: synthesize (optionally via human review) or loop back
    graph.add_conditional_edges(
        "confidence_evaluator",
        _should_continue,
        {
            "synthesize": "human_review" if with_hitl else "synthesis",
            "re_retrieve": "vector_retrieval",
        },
    )

    if with_hitl:
        graph.add_node("human_review", human_review)
        graph.add_conditional_edges(
            "human_review",
            after_human_review,
            {"approved": "synthesis", "rejected": "output_guardrail"},
        )

    graph.add_edge("synthesis", "output_guardrail")
    graph.add_edge("output_guardrail", END)

    return graph.compile(checkpointer=get_checkpointer())


@lru_cache(maxsize=4)
def _cached_graph(tracing: bool, with_hitl: bool) -> Any:
    return build_healthcare_graph(with_hitl=with_hitl)


def get_compiled_graph() -> Any:
    """Return the compiled graph for the current tracing/HITL configuration.

    Compilation is done once per configuration; nodes resolve their runtime
    dependencies at call time, so a cached graph is safe to share.
    """
    return _cached_graph(mlflow_enabled(), hitl_enabled())


def clear_graph_cache() -> None:
    _cached_graph.cache_clear()


# ── Public runners ─────────────────────────────────────────────────────────

# Scalar fields from agent messages that are safe to stream before the
# role-based response sanitizer runs on the final payload.
_STEP_FIELDS = (
    "agent",
    "action",
    "request_type",
    "reason",
    "results_count",
    "patients_queried",
    "confidence",
    "iteration",
    "answer_length",
    "capability",
    "from_agent",
    "to_agent",
)


def _initial_state(
    question: str,
    patient_id: str | None,
    *,
    structured: bool,
    session_context: str,
    patient_memory: PatientMemoryRecord | None = None,
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
) -> HealthcareAgentState:
    return {
        "question": question,
        "patient_id": patient_id,
        "structured": structured,
        "session_context": session_context,
        "_patient_memory_record": patient_memory,
        "patient_memory_context": [],
        "patient_memory_facts": [],
        "patient_memory_policy": {},
        "patient_memory_metadata": {"loaded": False},
        "context_limit": context_limit,
        "vector_context": [],
        "graph_context": [],
        "patient_ids": [],
        "messages": [],
        "confidence": 0.0,
        "iteration": 0,
    }


def _run_config(patient_id: str | None, *, thread_id: str | None = None) -> dict[str, Any]:
    config: dict[str, Any] = {"recursion_limit": _recursion_limit()}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}
    return config


def public_step(node: str, update: dict[str, Any] | None) -> dict[str, Any]:
    """Project a node update to a small, evidence-free progress event."""
    if node == "__interrupt__":
        return {"node": "human_review", "messages": [{"agent": "human_review", "action": "pending"}]}
    messages = (update or {}).get("messages") or []
    return {
        "node": node,
        "messages": [
            {
                key: msg[key]
                for key in _STEP_FIELDS
                if key in msg and isinstance(msg[key], (str, int, float, bool))
            }
            for msg in messages
            if isinstance(msg, dict)
        ],
    }


def final_state_to_response(
    question: str,
    final_state: dict[str, Any],
    *,
    thread_id: str | None = None,
    pending_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Map final graph state to the ``run_query`` response shape.

    ``pending_review`` is the interrupt payload of a run paused for clinician
    review; the response then carries ``status="pending_approval"`` and the
    ``thread_id`` needed to resume it.
    """
    # Deduplicate patient_ids that may have been appended from multiple iterations
    patient_ids = sorted(set(final_state.get("patient_ids", [])))
    response: dict[str, Any] = {
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
        "patient_memory_context": final_state.get("patient_memory_context", []),
        "answer": PENDING_ANSWER if pending_review else final_state.get("answer", ""),
        "guardrails": dict(final_state.get("guardrails") or {}),
        "status": "pending_approval" if pending_review else "completed",
        "langgraph": {
            "enabled": True,
            "iterations": final_state.get("iteration", 0),
            "final_reason": (
                "pending_review" if pending_review else final_state.get("final_reason", "unknown")
            ),
            "confidence": final_state.get("confidence", 0.0),
            "agent_trace": final_state.get("messages", []),
        },
    }
    if thread_id:
        response["thread_id"] = thread_id
    if pending_review:
        response["human_review"] = {"status": "pending", **pending_review}
    elif final_state.get("human_review"):
        response["human_review"] = dict(final_state["human_review"])
    if final_state.get("structured_response") and not pending_review:
        response["structured_response"] = final_state["structured_response"]
    return response


def run_langgraph_query(
    question: str,
    patient_id: str | None = None,
    *,
    structured: bool = False,
    session_context: str = "",
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
) -> dict[str, Any]:
    """Execute the healthcare multi-agent graph and return a response dict
    compatible with the existing ``run_query`` output shape.

    When ``MLFLOW_TRACKING_URI`` is set, the full pipeline is traced as
    an MLflow span hierarchy visible in the MLflow Tracing UI.
    """
    from healthcare_agent.observability.tracing import trace_query

    def _invoke(q, pid):
        return _run_langgraph_pipeline(
            q, pid, structured=structured, session_context=session_context, context_limit=context_limit
        )

    if mlflow_enabled():
        return trace_query(question, patient_id, "langgraph", _invoke)
    return _invoke(question, patient_id)


def _run_langgraph_pipeline(
    question: str,
    patient_id: str | None = None,
    *,
    structured: bool = False,
    session_context: str = "",
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
) -> dict[str, Any]:
    """Inner pipeline — separated so MLflow can wrap the full execution."""
    from healthcare_agent.orchestration.orchestrator import LangGraphOrchestrator

    return LangGraphOrchestrator(get_compiled_graph()).run(
        question,
        patient_id,
        structured=structured,
        session_context=session_context,
        context_limit=context_limit,
    )


def stream_langgraph_query(
    question: str,
    patient_id: str | None = None,
    *,
    structured: bool = False,
    session_context: str = "",
    context_limit: int = DEFAULT_CONTEXT_LIMIT,
) -> Iterator[tuple[str, dict[str, Any]]]:
    """Run the graph, yielding ``("step", event)`` per node then ``("result", response)``."""
    from healthcare_agent.orchestration.orchestrator import LangGraphOrchestrator

    yield from LangGraphOrchestrator(get_compiled_graph()).stream(
        question,
        patient_id,
        structured=structured,
        session_context=session_context,
        context_limit=context_limit,
    )
