"""Specialized agent nodes for the LangGraph healthcare multi-agent graph.

Each function is a LangGraph *node* that receives and returns
``HealthcareAgentState``.  Nodes are composable: the graph wires them
through conditional edges based on ``request_type`` and ``confidence``.
"""
from __future__ import annotations

from typing import Any

from .state import HealthcareAgentState


# ── Supervisor / Triage Agent ───────────────────────────────────────────────

def triage_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Classify the question and produce an initial retrieval plan.

    Sets ``request_type``, ``plan_query_text``, ``plan_top_k``, ``plan_reason``
    and emits a reasoning message.
    """
    from domain import classify_request_type, select_retrieval_plan

    question = state["question"]
    patient_id = state.get("patient_id")

    request_type = classify_request_type(question, patient_id)
    plan = select_retrieval_plan(request_type, question, patient_id, 5)

    return {
        "request_type": request_type,
        "plan_query_text": plan.query_text,
        "plan_top_k": plan.top_k,
        "plan_reason": plan.reason,
        "messages": [{
            "agent": "triage",
            "action": "classify",
            "request_type": request_type,
            "reason": plan.reason,
        }],
    }


# ── Vector Retrieval Agent ──────────────────────────────────────────────────

def vector_retrieval_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Run vector similarity search against Qdrant using the plan query."""
    from app import vector_context
    from domain import rank_vector_context

    query_text = state.get("plan_query_text", state["question"])
    patient_id = state.get("patient_id")
    top_k = state.get("plan_top_k", 5)
    request_type = state.get("request_type", "patient_summary")

    raw = vector_context(query_text, patient_id, top_k)
    ranked = rank_vector_context(raw, request_type)

    patient_ids = list({
        item["patient_id"] for item in ranked if item.get("patient_id")
    })
    if patient_id and patient_id not in patient_ids:
        patient_ids.append(patient_id)

    return {
        "vector_context": ranked,
        "patient_ids": patient_ids,
        "messages": [{
            "agent": "vector_retrieval",
            "action": "search",
            "results_count": len(ranked),
            "patient_ids_found": patient_ids,
        }],
    }


# ── Graph Retrieval Agent ──────────────────────────────────────────────────

def graph_retrieval_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Query Neo4j patient graph for patients discovered so far."""
    from app import graph_context
    from domain import rank_graph_context

    patient_ids = list(set(state.get("patient_ids", [])))
    request_type = state.get("request_type", "patient_summary")

    if not patient_ids:
        return {
            "messages": [{
                "agent": "graph_retrieval",
                "action": "skip",
                "reason": "no patient IDs available",
            }],
        }

    raw = graph_context(patient_ids)
    ranked = rank_graph_context(raw, request_type)

    return {
        "graph_context": ranked,
        "messages": [{
            "agent": "graph_retrieval",
            "action": "query",
            "patients_queried": len(patient_ids),
            "results_count": len(ranked),
        }],
    }


# ── Medication Safety Agent ────────────────────────────────────────────────

def medication_safety_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Deep-dive into medication interactions, contraindications, and adverse events."""
    graph_ctx = state.get("graph_context", [])

    risks: list[dict[str, Any]] = []
    for patient in graph_ctx:
        pid = patient.get("patient_id", "unknown")
        interactions = patient.get("interactions", [])
        adverse = patient.get("adverse_events", [])
        contras = patient.get("contraindications", [])
        if interactions or adverse or contras:
            risks.append({
                "patient_id": pid,
                "interaction_count": len(interactions),
                "adverse_event_count": len(adverse),
                "contraindication_count": len(contras),
                "interactions": interactions,
                "adverse_events": adverse,
                "contraindications": contras,
            })

    return {
        "messages": [{
            "agent": "medication_safety",
            "action": "assess",
            "patients_with_risks": len(risks),
            "risks": risks,
        }],
    }


# ── Lab Interpretation Agent ───────────────────────────────────────────────

def lab_interpretation_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Extract and interpret lab signals and abnormal observations."""
    graph_ctx = state.get("graph_context", [])

    signals: list[dict[str, Any]] = []
    for patient in graph_ctx:
        pid = patient.get("patient_id", "unknown")
        lab_signals = patient.get("lab_signals", [])
        abnormal_obs = [
            obs for obs in patient.get("observations", []) if obs.get("abnormal")
        ]
        if lab_signals or abnormal_obs:
            signals.append({
                "patient_id": pid,
                "lab_signal_count": len(lab_signals),
                "abnormal_observation_count": len(abnormal_obs),
                "lab_signals": lab_signals,
                "abnormal_observations": abnormal_obs,
            })

    return {
        "messages": [{
            "agent": "lab_interpretation",
            "action": "analyze",
            "patients_with_signals": len(signals),
            "signals": signals,
        }],
    }


# ── Coding Review Agent ───────────────────────────────────────────────────

def coding_review_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Analyze claims, coding gaps, and ICD-10 mapping for denial prevention."""
    graph_ctx = state.get("graph_context", [])

    reviews: list[dict[str, Any]] = []
    for patient in graph_ctx:
        pid = patient.get("patient_id", "unknown")
        claims = patient.get("claims", [])
        icd10 = patient.get("icd10_codes", [])
        conditions = patient.get("conditions", [])

        coded_conditions = {c.get("condition") for c in icd10 if c.get("condition")}
        condition_names = {
            c.get("name") if isinstance(c, dict) else str(c)
            for c in conditions
        }
        uncoded = condition_names - coded_conditions

        if claims or uncoded:
            reviews.append({
                "patient_id": pid,
                "claim_count": len(claims),
                "icd10_mapped": len(icd10),
                "uncoded_conditions": sorted(uncoded),
                "claims": claims,
            })

    return {
        "messages": [{
            "agent": "coding_review",
            "action": "review",
            "patients_reviewed": len(reviews),
            "reviews": reviews,
        }],
    }


# ── Confidence Evaluator ──────────────────────────────────────────────────

def confidence_evaluator(state: HealthcareAgentState) -> dict[str, Any]:
    """Estimate retrieval confidence and decide whether to iterate or finalize."""
    vector_ctx = state.get("vector_context", [])
    graph_ctx = state.get("graph_context", [])
    iteration = state.get("iteration", 0)

    if vector_ctx and graph_ctx:
        confidence = 1.0
    elif vector_ctx or graph_ctx:
        confidence = 0.5
    else:
        confidence = 0.0

    return {
        "confidence": confidence,
        "iteration": iteration + 1,
        "messages": [{
            "agent": "confidence_evaluator",
            "action": "evaluate",
            "confidence": confidence,
            "iteration": iteration + 1,
        }],
    }


# ── Synthesis Agent ────────────────────────────────────────────────────────

def synthesis_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Generate the final grounded answer from collected evidence."""
    from app import ask_ollama

    question = state["question"]
    vector_ctx = state.get("vector_context", [])
    graph_ctx = state.get("graph_context", [])

    answer = ask_ollama(question, vector_ctx, graph_ctx)

    return {
        "answer": answer,
        "final_reason": "synthesis_complete",
        "messages": [{
            "agent": "synthesis",
            "action": "generate",
            "answer_length": len(answer),
        }],
    }
