"""Tests for inter-agent delegation protocol."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langgraph_agents.agent_cards import (
    AGENT_REGISTRY,
    AgentCard,
    DelegationRequest,
    DelegationResponse,
    discover_agents,
    resolve_delegation,
)
from langgraph_agents.agents import (
    lab_interpretation_agent,
    medication_safety_agent,
)


class AgentCardTests(unittest.TestCase):
    def test_registry_has_all_agents(self):
        expected = {"triage", "vector_retrieval", "graph_retrieval", "medication_safety",
                    "lab_interpretation", "coding_review", "synthesis"}
        self.assertEqual(set(AGENT_REGISTRY.keys()), expected)

    def test_can_handle_returns_true_for_declared_capability(self):
        card = AGENT_REGISTRY["medication_safety"]
        self.assertTrue(card.can_handle("drug_interaction"))

    def test_can_handle_returns_false_for_undeclared(self):
        card = AGENT_REGISTRY["medication_safety"]
        self.assertFalse(card.can_handle("lab_signal"))

    def test_discover_agents_finds_renal_function(self):
        agents = discover_agents("renal_function")
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, "lab_interpretation")

    def test_discover_agents_returns_empty_for_unknown(self):
        self.assertEqual(discover_agents("time_travel"), [])


class DelegationRequestResponseTests(unittest.TestCase):
    def test_request_to_dict(self):
        req = DelegationRequest(
            from_agent="medication_safety",
            to_agent="lab_interpretation",
            capability="renal_function",
            query="Check creatinine",
        )
        d = req.to_dict()
        self.assertEqual(d["type"], "delegation_request")
        self.assertEqual(d["from_agent"], "medication_safety")
        self.assertEqual(d["to_agent"], "lab_interpretation")

    def test_response_to_dict(self):
        resp = DelegationResponse(
            from_agent="lab_interpretation",
            to_agent="medication_safety",
            capability="renal_function",
            result={"creatinine": 4.2},
            confidence=0.9,
        )
        d = resp.to_dict()
        self.assertEqual(d["type"], "delegation_response")
        self.assertEqual(d["confidence"], 0.9)

    def test_resolve_delegation_finds_target(self):
        req = DelegationRequest(
            from_agent="medication_safety",
            to_agent="lab_interpretation",
            capability="renal_function",
            query="Check renal",
        )
        self.assertEqual(resolve_delegation(req), "lab_interpretation")

    def test_resolve_delegation_discovers_by_capability(self):
        req = DelegationRequest(
            from_agent="medication_safety",
            to_agent="nonexistent",
            capability="renal_function",
            query="Check renal",
        )
        self.assertEqual(resolve_delegation(req), "lab_interpretation")


class MedicationSafetyDelegationTests(unittest.TestCase):
    def test_emits_renal_delegation_for_nephrotoxic_contraindication(self):
        state = {
            "graph_context": [{
                "patient_id": "p1",
                "interactions": [],
                "adverse_events": [],
                "contraindications": [{"medication": "Metformin", "reason": "lactic_acidosis_risk", "severity": "high"}],
            }],
            "delegation_responses": [],
        }
        result = medication_safety_agent(state)
        delegations = result.get("delegation_requests", [])
        self.assertEqual(len(delegations), 1)
        self.assertEqual(delegations[0]["to_agent"], "lab_interpretation")
        self.assertEqual(delegations[0]["capability"], "renal_function")

    def test_no_delegation_when_no_renal_contraindication(self):
        state = {
            "graph_context": [{
                "patient_id": "p1",
                "interactions": [{"drug_a": "Warfarin", "drug_b": "Aspirin"}],
                "adverse_events": [],
                "contraindications": [],
            }],
            "delegation_responses": [],
        }
        result = medication_safety_agent(state)
        self.assertEqual(result.get("delegation_requests", []), [])

    def test_uses_lab_context_from_delegation_response(self):
        state = {
            "graph_context": [{
                "patient_id": "p1",
                "interactions": [{"drug_a": "A", "drug_b": "B"}],
                "adverse_events": [],
                "contraindications": [{"reason": "lactic_acidosis_risk"}],
            }],
            "delegation_responses": [{
                "from_agent": "lab_interpretation",
                "to_agent": "medication_safety",
                "capability": "renal_function",
                "result": {"creatinine": 4.2, "renal_markers": [{"name": "Creatinine", "value": 4.2}]},
                "confidence": 0.9,
            }],
        }
        result = medication_safety_agent(state)
        risks = result["messages"][0]["risks"]
        self.assertIn("lab_context", risks[0])


class LabInterpretationDelegationTests(unittest.TestCase):
    def test_responds_to_renal_function_delegation(self):
        state = {
            "graph_context": [{
                "patient_id": "p1",
                "lab_signals": [{"observation": "Creatinine", "indicated_condition": "Chronic Kidney Disease", "value": 4.2}],
                "observations": [
                    {"name": "Creatinine", "value": 4.2, "abnormal": True},
                    {"name": "Glucose", "value": 100, "abnormal": False},
                ],
            }],
            "delegation_requests": [{
                "from_agent": "medication_safety",
                "to_agent": "lab_interpretation",
                "capability": "renal_function",
                "query": "Assess renal function",
                "context": {"patient_id": "p1"},
            }],
        }
        result = lab_interpretation_agent(state)
        responses = result.get("delegation_responses", [])
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["capability"], "renal_function")
        self.assertGreater(responses[0]["result"]["marker_count"], 0)

    def test_responds_to_hepatic_function_delegation(self):
        state = {
            "graph_context": [{
                "patient_id": "p1",
                "lab_signals": [],
                "observations": [
                    {"name": "ALT", "value": 120, "abnormal": True},
                    {"name": "AST", "value": 95, "abnormal": True},
                ],
            }],
            "delegation_requests": [{
                "from_agent": "medication_safety",
                "to_agent": "lab_interpretation",
                "capability": "hepatic_function",
                "query": "Assess hepatic function",
                "context": {"patient_id": "p1"},
            }],
        }
        result = lab_interpretation_agent(state)
        responses = result.get("delegation_responses", [])
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["capability"], "hepatic_function")
        self.assertEqual(responses[0]["result"]["marker_count"], 2)

    def test_ignores_delegations_to_other_agents(self):
        state = {
            "graph_context": [],
            "delegation_requests": [{
                "from_agent": "coding_review",
                "to_agent": "medication_safety",
                "capability": "drug_interaction",
                "query": "Check interactions",
                "context": {},
            }],
        }
        result = lab_interpretation_agent(state)
        self.assertEqual(result.get("delegation_responses", []), [])


if __name__ == "__main__":
    unittest.main()
