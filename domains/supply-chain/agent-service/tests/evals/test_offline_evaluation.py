from __future__ import annotations

from supply_chain_agent.evaluation.scenarios import (
    EVALUATION_DATASET,
    evaluate_agent_coverage,
    evaluate_answer_quality,
    evaluate_evidence_completeness,
    evaluate_routing_accuracy,
)
from supply_chain_agent.orchestration.planner import classify_request_type


def test_dataset_covers_all_supported_request_types() -> None:
    expected = {case["expected_type"] for case in EVALUATION_DATASET}
    assert expected == {
        "supplier_risk",
        "shipment_tracking",
        "quality_review",
        "disruption_impact",
        "inventory_planning",
    }


def test_offline_scenarios_score_expected_contracts() -> None:
    for case in EVALUATION_DATASET:
        request_type = classify_request_type(case["question"], case.get("entity_id"))
        trace = [{"agent": "triage", "request_type": request_type}]
        trace.extend({"agent": agent} for agent in case["expected_agents"] if agent != "triage")
        result = {
            "answer": "Synthetic evidence supports this assessment. Verify before operational use.",
            "vector_context": [{"text": "synthetic vector evidence"}],
            "graph_context": [{"entity_id": case.get("entity_id")}],
        }
        assert evaluate_routing_accuracy(trace, case["expected_type"])["score"] == 1.0
        assert evaluate_agent_coverage(trace, case["expected_agents"])["score"] == 1.0
        assert evaluate_evidence_completeness(result)["score"] == 1.0
        assert evaluate_answer_quality(result)["score"] == 1.0