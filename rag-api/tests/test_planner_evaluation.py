from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.planner import classify_request_type, select_retrieval_plan


class PlannerEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        fixture_path = Path(__file__).resolve().parent / "fixtures" / "planner_route_fixtures.json"
        cls.fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))

    def test_route_selection_fixtures(self) -> None:
        for case in self.fixtures:
            with self.subTest(case_id=case["id"]):
                request_type = classify_request_type(case["question"], case["patient_id"])
                self.assertEqual(request_type, case["expected_request_type"])

    def test_plan_selection_fixtures(self) -> None:
        for case in self.fixtures:
            with self.subTest(case_id=case["id"]):
                request_type = classify_request_type(case["question"], case["patient_id"])
                plan = select_retrieval_plan(
                    request_type,
                    case["question"],
                    case["patient_id"],
                    case["max_top_k"],
                )
                self.assertEqual(plan.name, case["expected_plan_name"])
                self.assertEqual(plan.top_k, case["expected_top_k"])
                self.assertTrue(plan.query_text.startswith(case["expected_query_prefix"]))
                self.assertIn(case["expected_reason_contains"], plan.reason)
                self.assertLessEqual(plan.top_k, case["max_top_k"])
                self.assertGreaterEqual(plan.top_k, 1)


if __name__ == "__main__":
    unittest.main()
