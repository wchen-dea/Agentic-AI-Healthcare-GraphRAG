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
