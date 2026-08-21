"""Unit tests for the LangGraph healthcare multi-agent system.

Tests the graph structure, agent routing, state management, and evaluation
without requiring live infrastructure (Qdrant, Neo4j, Ollama).
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from langgraph_agents.agents import (
    coding_review_agent,
    confidence_evaluator,
    graph_retrieval_agent,
    lab_interpretation_agent,
    medication_safety_agent,
    synthesis_agent,
    triage_agent,
    vector_retrieval_agent,
)
from langgraph_agents.evaluation import (
    evaluate_agent_coverage,
    evaluate_answer_quality,
    evaluate_evidence_completeness,
    evaluate_routing_accuracy,
)
from langgraph_agents.graph import _route_specialist, _should_continue
from langgraph_agents.state import HealthcareAgentState


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture
def base_state() -> HealthcareAgentState:
    return {
        "question": "What medications is patient P-001 taking?",
        "patient_id": "P-001",
        "vector_context": [],
        "graph_context": [],
        "patient_ids": [],
        "messages": [],
        "confidence": 0.0,
        "iteration": 0,
    }


@pytest.fixture
def populated_state() -> HealthcareAgentState:
    return {
        "question": "What medications is patient P-001 taking?",
        "patient_id": "P-001",
        "request_type": "medication_safety",
        "plan_query_text": "Medication safety focus: What medications is patient P-001 taking?",
        "plan_top_k": 5,
        "plan_reason": "Question contains medication safety semantics.",
        "vector_context": [
            {"event_id": "e1", "patient_id": "P-001", "event_type": "medication_order", "score": 0.95},
        ],
        "graph_context": [
            {
                "patient_id": "P-001",
                "conditions": [{"name": "Hypertension"}],
                "medications": [{"medication": "Lisinopril", "dose": "10mg"}],
                "interactions": [{"from": "Lisinopril", "to": "Spironolactone", "risk": "high", "severity": "major"}],
                "adverse_events": [],
                "contraindications": [],
                "observations": [],
                "symptoms": [],
                "lab_signals": [],
                "icd10_codes": [{"condition": "Hypertension", "icd10": "I10"}],
                "claims": [],
                "vitals": [],
            },
        ],
        "patient_ids": ["P-001"],
        "messages": [],
        "confidence": 0.0,
        "iteration": 0,
    }


# ── Triage agent tests ────────────────────────────────────────────────────

class TestTriageAgent:
    @patch("domain.planner.classify_request_type", return_value="medication_safety")
    @patch("domain.planner.select_retrieval_plan")
    def test_classifies_medication_question(self, mock_plan, mock_classify, base_state):
        mock_plan.return_value = MagicMock(
            query_text="Medication safety focus: test",
            top_k=5,
            reason="medication semantics",
        )
        result = triage_agent(base_state)
        assert result["request_type"] == "medication_safety"
        assert len(result["messages"]) == 1
        assert result["messages"][0]["agent"] == "triage"

    @patch("domain.planner.classify_request_type", return_value="patient_summary")
    @patch("domain.planner.select_retrieval_plan")
    def test_classifies_summary_question(self, mock_plan, mock_classify):
        mock_plan.return_value = MagicMock(
            query_text="test", top_k=5, reason="default"
        )
        state: HealthcareAgentState = {
            "question": "Summarize patient P-002",
            "patient_id": "P-002",
            "vector_context": [],
            "graph_context": [],
            "patient_ids": [],
            "messages": [],
            "confidence": 0.0,
            "iteration": 0,
        }
        result = triage_agent(state)
        assert result["request_type"] == "patient_summary"


# ── Specialist agent tests ─────────────────────────────────────────────────

class TestMedicationSafetyAgent:
    def test_extracts_medication_risks(self, populated_state):
        result = medication_safety_agent(populated_state)
        msg = result["messages"][0]
        assert msg["agent"] == "medication_safety"
        assert msg["patients_with_risks"] == 1
        assert msg["risks"][0]["interaction_count"] == 1

    def test_no_risks_when_empty(self, base_state):
        base_state["graph_context"] = [{"patient_id": "P-001", "interactions": [], "adverse_events": [], "contraindications": []}]
        result = medication_safety_agent(base_state)
        assert result["messages"][0]["patients_with_risks"] == 0


class TestLabInterpretationAgent:
    def test_extracts_lab_signals(self):
        state: HealthcareAgentState = {
            "question": "labs",
            "graph_context": [{
                "patient_id": "P-002",
                "lab_signals": [{"observation": "potassium", "value": "6.1", "indicated_condition": "Hyperkalemia"}],
                "observations": [{"name": "potassium", "value": "6.1", "abnormal": True}],
            }],
            "vector_context": [],
            "patient_ids": [],
            "messages": [],
            "confidence": 0.0,
            "iteration": 0,
        }
        result = lab_interpretation_agent(state)
        msg = result["messages"][0]
        assert msg["patients_with_signals"] == 1
        assert msg["signals"][0]["lab_signal_count"] == 1


class TestCodingReviewAgent:
    def test_detects_uncoded_conditions(self):
        state: HealthcareAgentState = {
            "question": "coding gaps",
            "graph_context": [{
                "patient_id": "P-004",
                "conditions": [{"name": "Diabetes"}, {"name": "Asthma"}],
                "icd10_codes": [{"condition": "Diabetes", "icd10": "E11"}],
                "claims": [{"status": "submitted"}],
            }],
            "vector_context": [],
            "patient_ids": [],
            "messages": [],
            "confidence": 0.0,
            "iteration": 0,
        }
        result = coding_review_agent(state)
        msg = result["messages"][0]
        assert "Asthma" in msg["reviews"][0]["uncoded_conditions"]


# ── Confidence evaluator tests ─────────────────────────────────────────────

class TestConfidenceEvaluator:
    def test_full_confidence_when_both_channels(self, populated_state):
        result = confidence_evaluator(populated_state)
        assert result["confidence"] == 1.0

    def test_half_confidence_when_vector_only(self, base_state):
        base_state["vector_context"] = [{"event_id": "e1"}]
        result = confidence_evaluator(base_state)
        assert result["confidence"] == 0.5

    def test_zero_confidence_when_empty(self, base_state):
        result = confidence_evaluator(base_state)
        assert result["confidence"] == 0.0

    def test_increments_iteration(self, base_state):
        base_state["iteration"] = 2
        result = confidence_evaluator(base_state)
        assert result["iteration"] == 3


# ── Routing logic tests ───────────────────────────────────────────────────

class TestRouting:
    def test_route_medication_safety(self):
        assert _route_specialist({"request_type": "medication_safety"}) == "medication_safety"

    def test_route_lab_interpretation(self):
        assert _route_specialist({"request_type": "lab_interpretation"}) == "lab_interpretation"

    def test_route_coding_review(self):
        assert _route_specialist({"request_type": "coding_review"}) == "coding_review"

    def test_route_default_to_confidence(self):
        assert _route_specialist({"request_type": "patient_summary"}) == "confidence_evaluator"
        assert _route_specialist({"request_type": "cohort_triage"}) == "confidence_evaluator"

    @patch.dict("os.environ", {"LANGGRAPH_MAX_ITERATIONS": "3"})
    def test_should_synthesize_on_high_confidence(self):
        assert _should_continue({"confidence": 0.9, "iteration": 1}) == "synthesize"

    @patch.dict("os.environ", {"LANGGRAPH_MAX_ITERATIONS": "3"})
    def test_should_synthesize_on_max_iterations(self):
        assert _should_continue({"confidence": 0.3, "iteration": 3}) == "synthesize"

    @patch.dict("os.environ", {"LANGGRAPH_MAX_ITERATIONS": "3"})
    def test_should_re_retrieve_on_low_confidence(self):
        assert _should_continue({"confidence": 0.3, "iteration": 1}) == "re_retrieve"


# ── Evaluation scoring tests ──────────────────────────────────────────────

class TestEvaluation:
    def test_routing_accuracy_correct(self):
        trace = [{"agent": "triage", "request_type": "medication_safety"}]
        result = evaluate_routing_accuracy(trace, "medication_safety")
        assert result["score"] == 1.0

    def test_routing_accuracy_wrong(self):
        trace = [{"agent": "triage", "request_type": "patient_summary"}]
        result = evaluate_routing_accuracy(trace, "medication_safety")
        assert result["score"] == 0.0

    def test_agent_coverage_full(self):
        trace = [
            {"agent": "triage"},
            {"agent": "vector_retrieval"},
            {"agent": "graph_retrieval"},
            {"agent": "medication_safety"},
        ]
        expected = ["triage", "vector_retrieval", "graph_retrieval", "medication_safety"]
        result = evaluate_agent_coverage(trace, expected)
        assert result["score"] == 1.0

    def test_agent_coverage_partial(self):
        trace = [{"agent": "triage"}, {"agent": "vector_retrieval"}]
        expected = ["triage", "vector_retrieval", "graph_retrieval"]
        result = evaluate_agent_coverage(trace, expected)
        assert abs(result["score"] - 2 / 3) < 0.01

    def test_evidence_completeness_both(self):
        result = evaluate_evidence_completeness(
            {"vector_context": [{"x": 1}], "graph_context": [{"y": 2}]}
        )
        assert result["score"] == 1.0

    def test_evidence_completeness_none(self):
        result = evaluate_evidence_completeness(
            {"vector_context": [], "graph_context": []}
        )
        assert result["score"] == 0.0

    def test_answer_quality_good(self):
        answer = "The patient has hypertension managed with Lisinopril. " * 3
        result = evaluate_answer_quality({"answer": answer})
        assert result["score"] == 1.0

    def test_answer_quality_error(self):
        result = evaluate_answer_quality({"answer": "LLM error: timeout"})
        assert result["score"] == 0.0


# ── Polypharmacy medication safety scenario tests ─────────────────────────

class TestPolypharmacyScenario:
    """Tests for the primary multi-agent use case: polypharmacy patient with
    anticoagulant + antiplatelet + dual potassium-sparing agents, CKD, and
    abnormal labs."""

    @pytest.fixture
    def polypharmacy_state(self) -> HealthcareAgentState:
        return {
            "question": "Review medication safety: are there dangerous interactions or contraindications for this patient given their current labs and conditions?",
            "patient_id": "patient-0001",
            "request_type": "medication_safety",
            "plan_query_text": "Medication safety focus: Review medication safety",
            "plan_top_k": 6,
            "plan_reason": "Question contains medication safety semantics.",
            "vector_context": [
                {"event_id": "e1", "patient_id": "patient-0001", "event_type": "medication_order", "score": 0.92},
                {"event_id": "e2", "patient_id": "patient-0001", "event_type": "medication_order", "score": 0.88},
                {"event_id": "e3", "patient_id": "patient-0001", "event_type": "lab_result", "score": 0.85},
            ],
            "graph_context": [
                {
                    "patient_id": "patient-0001",
                    "age": 72,
                    "sex": "M",
                    "risk_tier": "high",
                    "conditions": [
                        {"name": "Chronic Kidney Disease"},
                        {"name": "Hyperkalemia"},
                        {"name": "Hypertension"},
                    ],
                    "symptoms": ["dizziness"],
                    "observations": [
                        {"name": "Potassium", "value": "6.1", "unit": "mmol/L", "abnormal": True},
                        {"name": "Creatinine", "value": "1.8", "unit": "mg/dL", "abnormal": True},
                    ],
                    "medications": [
                        {"medication": "Warfarin", "drug_class": "Anticoagulant", "dose": "5mg", "route": "oral", "order_type": "ordered"},
                        {"medication": "Aspirin", "drug_class": "Antiplatelet", "dose": "81mg", "route": "oral", "order_type": "ordered"},
                        {"medication": "Lisinopril", "drug_class": "ACE Inhibitor", "dose": "10mg", "route": "oral", "order_type": "ordered"},
                        {"medication": "Spironolactone", "drug_class": "Potassium-Sparing Diuretic", "dose": "25mg", "route": "oral", "order_type": "ordered"},
                    ],
                    "interactions": [
                        {"from": "Warfarin", "to": "Aspirin", "risk": "bleeding_risk", "severity": "high"},
                        {"from": "Lisinopril", "to": "Spironolactone", "risk": "hyperkalemia_risk", "severity": "moderate"},
                    ],
                    "adverse_events": [
                        {"symptom": "dizziness", "medication": "Lisinopril", "severity": "low", "meddra_term": "Dizziness"},
                    ],
                    "contraindications": [
                        {"medication": "Lisinopril", "condition": "Hyperkalemia", "reason": "worsens_hyperkalemia", "severity": "high"},
                        {"medication": "Spironolactone", "condition": "Hyperkalemia", "reason": "worsens_hyperkalemia", "severity": "high"},
                    ],
                    "lab_signals": [
                        {"observation": "Potassium", "value": "6.1", "unit": "mmol/L", "indicated_condition": "Hyperkalemia", "reason": "elevated_potassium"},
                        {"observation": "Creatinine", "value": "1.8", "unit": "mg/dL", "indicated_condition": "Chronic Kidney Disease", "reason": "elevated_creatinine"},
                    ],
                    "icd10_codes": [
                        {"condition": "Chronic Kidney Disease", "icd10": "N18.9"},
                        {"condition": "Hypertension", "icd10": "I10"},
                    ],
                    "claims": [],
                    "vitals": [],
                },
            ],
            "patient_ids": ["patient-0001"],
            "messages": [],
            "confidence": 0.0,
            "iteration": 0,
        }

    def test_triage_routes_to_medication_safety(self, polypharmacy_state):
        result = _route_specialist(polypharmacy_state)
        assert result == "medication_safety"

    def test_medication_agent_extracts_interactions(self, polypharmacy_state):
        result = medication_safety_agent(polypharmacy_state)
        msg = result["messages"][0]
        assert msg["agent"] == "medication_safety"
        assert msg["patients_with_risks"] == 1
        risks = msg["risks"][0]
        assert risks["interaction_count"] == 2
        assert risks["contraindication_count"] == 2

    def test_lab_agent_extracts_abnormal_potassium(self, polypharmacy_state):
        result = lab_interpretation_agent(polypharmacy_state)
        msg = result["messages"][0]
        assert msg["patients_with_signals"] == 1
        signals = msg["signals"][0]
        assert signals["lab_signal_count"] == 2
        assert signals["abnormal_observation_count"] == 2

    def test_coding_agent_finds_uncoded_hyperkalemia(self, polypharmacy_state):
        result = coding_review_agent(polypharmacy_state)
        msg = result["messages"][0]
        # Hyperkalemia is in conditions but not in icd10_codes → uncoded
        assert msg["patients_reviewed"] == 1
        assert "Hyperkalemia" in msg["reviews"][0]["uncoded_conditions"]

    def test_confidence_reaches_1_with_dual_evidence(self, polypharmacy_state):
        result = confidence_evaluator(polypharmacy_state)
        assert result["confidence"] == 1.0

    def test_full_agent_trace_covers_medication_path(self, polypharmacy_state):
        """The medication safety path should activate triage, both retrievers,
        and the medication_safety specialist."""
        from langgraph_agents.evaluation import evaluate_agent_coverage
        trace = [
            {"agent": "triage"},
            {"agent": "vector_retrieval"},
            {"agent": "graph_retrieval"},
            {"agent": "medication_safety"},
            {"agent": "confidence_evaluator"},
            {"agent": "synthesis"},
        ]
        expected = ["triage", "vector_retrieval", "graph_retrieval", "medication_safety"]
        result = evaluate_agent_coverage(trace, expected)
        assert result["score"] == 1.0

    def test_interaction_chain_warfarin_aspirin(self, polypharmacy_state):
        """Verify the Warfarin+Aspirin bleeding risk is surfaced."""
        result = medication_safety_agent(polypharmacy_state)
        risks = result["messages"][0]["risks"][0]
        interactions = risks["interactions"]
        bleeding = [i for i in interactions if i["risk"] == "bleeding_risk" and i["severity"] == "high"]
        assert len(bleeding) >= 1
        pair = bleeding[0]
        assert {pair["from"], pair["to"]} == {"Warfarin", "Aspirin"}

    def test_contraindication_chain_confirmed_by_lab(self, polypharmacy_state):
        """Verify contraindications for Hyperkalemia are present alongside
        the lab signal that confirms the condition."""
        graph = polypharmacy_state["graph_context"][0]
        contras = graph["contraindications"]
        hyperkalemia_contras = [c for c in contras if c["condition"] == "Hyperkalemia"]
        assert len(hyperkalemia_contras) == 2
        contra_meds = {c["medication"] for c in hyperkalemia_contras}
        assert contra_meds == {"Lisinopril", "Spironolactone"}
        lab_signals = graph["lab_signals"]
        potassium_signal = [s for s in lab_signals if s["indicated_condition"] == "Hyperkalemia"]
        assert len(potassium_signal) == 1
        assert float(potassium_signal[0]["value"]) >= 5.5
