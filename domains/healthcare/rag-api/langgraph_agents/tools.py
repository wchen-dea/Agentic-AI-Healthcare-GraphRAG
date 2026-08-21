"""LangGraph tool definitions wrapping the existing retrieval and synthesis
functions from the healthcare RAG API.

Each tool is a plain function decorated with ``@tool`` so LangGraph agent
nodes can bind them.  The functions delegate to the *same* retrieval helpers
used by the legacy single-pass and ReAct paths, ensuring parity.
"""
from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# Retrieval tools
# ---------------------------------------------------------------------------

@tool
def vector_search(question: str, patient_id: str | None = None, top_k: int = 5) -> list[dict[str, Any]]:
    """Search the Qdrant vector store for clinical events matching *question*.

    Returns scored event summaries.  Optionally scoped to one patient.
    """
    from app import vector_context  # deferred to avoid circular import at module level
    return vector_context(question, patient_id, top_k)


@tool
def graph_lookup(patient_ids: list[str]) -> list[dict[str, Any]]:
    """Retrieve the full patient graph context from Neo4j for one or more patients.

    Includes conditions, symptoms, observations, medications, interactions,
    vitals, claims, lab signals, ICD-10 codes, adverse events, and
    contraindications.
    """
    from app import graph_context
    return graph_context(patient_ids)


@tool
def classify_request(question: str, patient_id: str | None = None) -> dict[str, str]:
    """Classify a clinical question into a request type and retrieval plan.

    Returns ``request_type``, ``query_text``, ``top_k``, and ``reason``.
    """
    from domain import classify_request_type, select_retrieval_plan
    request_type = classify_request_type(question, patient_id)
    plan = select_retrieval_plan(request_type, question, patient_id, 5)
    return {
        "request_type": request_type,
        "query_text": plan.query_text,
        "top_k": plan.top_k,
        "reason": plan.reason,
    }


@tool
def medication_risk_check(patient_ids: list[str]) -> list[dict[str, Any]]:
    """Check active medication interactions and contraindications for patients.

    Returns interaction pairs, adverse events, and contraindicated medications.
    """
    from app import graph_context
    results = graph_context(patient_ids)
    risks: list[dict[str, Any]] = []
    for patient in results:
        pid = patient.get("patient_id", "unknown")
        interactions = patient.get("interactions", [])
        adverse = patient.get("adverse_events", [])
        contras = patient.get("contraindications", [])
        if interactions or adverse or contras:
            risks.append({
                "patient_id": pid,
                "interactions": interactions,
                "adverse_events": adverse,
                "contraindications": contras,
            })
    return risks


@tool
def lab_signal_check(patient_ids: list[str]) -> list[dict[str, Any]]:
    """Extract lab signals and abnormal observations for given patients."""
    from app import graph_context
    results = graph_context(patient_ids)
    signals: list[dict[str, Any]] = []
    for patient in results:
        pid = patient.get("patient_id", "unknown")
        lab_signals = patient.get("lab_signals", [])
        abnormal_obs = [
            obs for obs in patient.get("observations", []) if obs.get("abnormal")
        ]
        if lab_signals or abnormal_obs:
            signals.append({
                "patient_id": pid,
                "lab_signals": lab_signals,
                "abnormal_observations": abnormal_obs,
            })
    return signals


@tool
def synthesize_answer(question: str, vector_ctx: list[dict[str, Any]], graph_ctx: list[dict[str, Any]]) -> str:
    """Generate a grounded clinical answer using the Ollama LLM provider."""
    from app import ask_ollama
    return ask_ollama(question, vector_ctx, graph_ctx)


# Convenience accessor for importing all tools at once
ALL_TOOLS = [
    vector_search,
    graph_lookup,
    classify_request,
    medication_risk_check,
    lab_signal_check,
    synthesize_answer,
]
