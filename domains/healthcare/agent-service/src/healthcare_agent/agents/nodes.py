"""Specialized agent nodes for the LangGraph healthcare multi-agent graph.

Each function is a LangGraph *node* that receives and returns
``HealthcareAgentState``.  Nodes are composable: the graph wires them
through conditional edges based on ``request_type`` and ``confidence``.
"""
from __future__ import annotations

from typing import Any

from healthcare_agent.agents.registry import DelegationRequest, DelegationResponse
from healthcare_agent.orchestration.runtime import get_runtime
from healthcare_agent.orchestration.state import HealthcareAgentState

# ── Supervisor / Triage Agent ───────────────────────────────────────────────

def triage_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Classify the question and produce an initial retrieval plan."""
    from healthcare_agent.orchestration.planner import classify_request_type, select_retrieval_plan

    question = state["question"]
    patient_id = state.get("patient_id")

    request_type = classify_request_type(question, patient_id)
    plan = select_retrieval_plan(request_type, question, patient_id, state.get("context_limit", 5))

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
    from healthcare_agent.retrieval.ranking import rank_vector_context

    query_text = state.get("plan_query_text", state["question"])
    patient_id = state.get("patient_id")
    top_k = state.get("plan_top_k", 5)
    request_type = state.get("request_type", "patient_summary")

    raw = get_runtime().vector_search(query_text, patient_id, top_k)
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
    from healthcare_agent.retrieval.ranking import rank_graph_context

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

    raw = get_runtime().graph_search(patient_ids)
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
    delegation_responses = state.get("delegation_responses", [])

    # Check for lab delegation responses from prior iterations
    lab_context: dict[str, Any] = {}
    for resp in delegation_responses:
        if resp.get("to_agent") == "medication_safety" and resp.get("capability") == "renal_function":
            lab_context = resp.get("result", {})

    risks: list[dict[str, Any]] = []
    delegation_requests: list[dict[str, Any]] = []

    for patient in graph_ctx:
        pid = patient.get("patient_id", "unknown")
        interactions = patient.get("interactions", [])
        adverse = patient.get("adverse_events", [])
        contras = patient.get("contraindications", [])

        # Delegate to lab agent when contraindicated drugs need renal/hepatic context
        needs_renal = any(
            c.get("reason", "").lower() in ("lactic_acidosis_risk", "worsens_hyperkalemia", "nephrotoxic")
            for c in contras
        )
        if needs_renal and not lab_context:
            delegation_requests.append(DelegationRequest(
                from_agent="medication_safety",
                to_agent="lab_interpretation",
                capability="renal_function",
                query=f"Assess renal function markers for patient {pid}",
                context={"patient_id": pid},
            ).to_dict())

        if interactions or adverse or contras:
            risk_entry: dict[str, Any] = {
                "patient_id": pid,
                "interaction_count": len(interactions),
                "adverse_event_count": len(adverse),
                "contraindication_count": len(contras),
                "interactions": interactions,
                "adverse_events": adverse,
                "contraindications": contras,
            }
            if lab_context:
                risk_entry["lab_context"] = lab_context
            risks.append(risk_entry)

    result: dict[str, Any] = {
        "messages": [{
            "agent": "medication_safety",
            "action": "assess",
            "patients_with_risks": len(risks),
            "delegations_emitted": len(delegation_requests),
            "risks": risks,
        }],
    }
    if delegation_requests:
        result["delegation_requests"] = delegation_requests
    return result


# ── Lab Interpretation Agent ───────────────────────────────────────────────

def lab_interpretation_agent(state: HealthcareAgentState) -> dict[str, Any]:
    """Extract and interpret lab signals and abnormal observations."""
    graph_ctx = state.get("graph_context", [])
    pending_delegations = state.get("delegation_requests", [])

    signals: list[dict[str, Any]] = []
    delegation_responses: list[dict[str, Any]] = []

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

    # Respond to delegation requests for specific capabilities
    for req in pending_delegations:
        if req.get("to_agent") != "lab_interpretation":
            continue
        capability = req.get("capability", "")
        req_pid = req.get("context", {}).get("patient_id")

        patient_signals = [s for s in signals if s.get("patient_id") == req_pid]
        if capability == "renal_function":
            renal_markers = []
            for ps in patient_signals:
                for obs in ps.get("abnormal_observations", []):
                    if obs.get("name", "").lower() in ("creatinine", "bun", "egfr"):
                        renal_markers.append(obs)
                for sig in ps.get("lab_signals", []):
                    if sig.get("indicated_condition", "").lower() in ("chronic kidney disease", "acute kidney injury"):
                        renal_markers.append(sig)
            delegation_responses.append(DelegationResponse(
                from_agent="lab_interpretation",
                to_agent=req.get("from_agent", ""),
                capability=capability,
                result={"patient_id": req_pid, "renal_markers": renal_markers, "marker_count": len(renal_markers)},
                confidence=0.9 if renal_markers else 0.3,
            ).to_dict())
        elif capability == "hepatic_function":
            hepatic_markers = []
            for ps in patient_signals:
                for obs in ps.get("abnormal_observations", []):
                    if obs.get("name", "").lower() in ("alt", "ast", "total bilirubin", "albumin", "alkaline phosphatase"):
                        hepatic_markers.append(obs)
            delegation_responses.append(DelegationResponse(
                from_agent="lab_interpretation",
                to_agent=req.get("from_agent", ""),
                capability=capability,
                result={"patient_id": req_pid, "hepatic_markers": hepatic_markers, "marker_count": len(hepatic_markers)},
                confidence=0.9 if hepatic_markers else 0.3,
            ).to_dict())

    result: dict[str, Any] = {
        "messages": [{
            "agent": "lab_interpretation",
            "action": "analyze",
            "patients_with_signals": len(signals),
            "delegations_resolved": len(delegation_responses),
            "signals": signals,
        }],
    }
    if delegation_responses:
        result["delegation_responses"] = delegation_responses
    return result


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
    from healthcare_agent.safety.response_policy import estimate_confidence

    vector_ctx = state.get("vector_context", [])
    graph_ctx = state.get("graph_context", [])
    iteration = state.get("iteration", 0)
    confidence = estimate_confidence(vector_ctx, graph_ctx)

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
    runtime = get_runtime()
    question = state["question"]
    session_context = state.get("session_context") or ""
    prompt_question = f"{session_context}\n\nCurrent question: {question}" if session_context else question
    vector_ctx = state.get("vector_context", [])
    graph_ctx = state.get("graph_context", [])

    result: dict[str, Any] = {"final_reason": "synthesis_complete"}
    if state.get("structured") and runtime.synthesize_structured is not None:
        structured = runtime.synthesize_structured(prompt_question, vector_ctx, graph_ctx)
        answer = str(structured.get("summary") or "")
        result["structured_response"] = structured
    else:
        answer = runtime.synthesize(prompt_question, vector_ctx, graph_ctx)

    result["answer"] = answer
    result["messages"] = [{
        "agent": "synthesis",
        "action": "generate_structured" if "structured_response" in result else "generate",
        "answer_length": len(answer),
    }]
    return result


# ── Guardrail nodes (deterministic policy; run before and after agents) ────

def input_guardrail(state: HealthcareAgentState) -> dict[str, Any]:
    """Block prompt injection and off-topic input before any tool executes."""
    from healthcare_agent.safety.guardrails import classify_input

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


def output_guardrail(state: HealthcareAgentState) -> dict[str, Any]:
    """Withhold unsafe generated answers before they leave the orchestrator."""
    from healthcare_agent.safety.guardrails import classify_output

    check = classify_output(state.get("answer", ""))
    guardrails = dict(state.get("guardrails") or {})
    if check.passed:
        guardrails["output_blocked"] = False
        return {
            "guardrails": guardrails,
            "messages": [{"agent": "output_guardrail", "action": "pass"}],
        }
    guardrails.update({"output_blocked": True, "category": check.category})
    return {
        "guardrails": guardrails,
        "answer": "Response withheld due to safety review.",
        "structured_response": {},
        "final_reason": "output_blocked",
        "messages": [{"agent": "output_guardrail", "action": "block", "reason": check.category}],
    }
