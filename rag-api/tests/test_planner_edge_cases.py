from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.evidence import rank_graph_context, rank_vector_context
from domain.planner import classify_request_type, select_retrieval_plan


class PlannerEdgeCaseTests(unittest.TestCase):
    def test_ambiguous_prompt_prefers_medication_route(self) -> None:
        question = "Medication interaction with high potassium lab and coding denial risk"
        request_type = classify_request_type(question, "patient-42")
        self.assertEqual(request_type, "medication_safety")

    def test_empty_patient_scope_transitions_to_cohort(self) -> None:
        question = "Summarize risk trend"
        request_type = classify_request_type(question, None)
        self.assertEqual(request_type, "cohort_triage")

        plan = select_retrieval_plan(request_type, question, None, max_top_k=4)
        self.assertEqual(plan.name, "cohort_triage")
        self.assertTrue(plan.query_text.startswith("Cohort triage focus (cohort):"))
        self.assertEqual(plan.top_k, 4)

    def test_plan_top_k_is_bounded_for_non_positive_inputs(self) -> None:
        plan = select_retrieval_plan(
            "patient_summary",
            "Provide patient update",
            "patient-9",
            max_top_k=0,
        )
        self.assertEqual(plan.top_k, 1)

    def test_vector_ranking_is_deterministic_by_priority_then_score_then_id(self) -> None:
        items = [
            {"event_type": "lab_result", "score": 0.9, "event_id": "evt-b"},
            {"event_type": "clinical_note", "score": 0.99, "event_id": "evt-a"},
            {"event_type": "lab_result", "score": 0.9, "event_id": "evt-a"},
            {"event_type": "vital_sign", "score": 0.91, "event_id": "evt-z"},
        ]
        ranked = rank_vector_context(items, "lab_interpretation")
        ordered_ids = [item["event_id"] for item in ranked]
        self.assertEqual(ordered_ids, ["evt-a", "evt-b", "evt-z", "evt-a"])

    def test_graph_ranking_is_deterministic_for_cohort(self) -> None:
        items = [
            {"patient_id": "patient-b", "conditions": ["c1"], "observations": [1, 2]},
            {"patient_id": "patient-a", "conditions": ["c1", "c2"], "observations": [1]},
            {"patient_id": "patient-c", "conditions": ["c1"], "observations": []},
        ]
        ranked = rank_graph_context(items, "cohort_triage")
        ordered = [item["patient_id"] for item in ranked]
        self.assertEqual(ordered, ["patient-a", "patient-b", "patient-c"])


if __name__ == "__main__":
    unittest.main()
