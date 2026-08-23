"""Tests for retrieval benchmark, grounding scorecard, and evidence fusion reranking."""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.retrieval_benchmark import precision_at_k, recall_at_k, evaluate_fixture, score_all, load_fixtures
from domain.grounding_scorecard import score_grounding
from domain.evidence import fusion_rerank


class PrecisionRecallTests(unittest.TestCase):
    def test_perfect_precision(self):
        self.assertEqual(precision_at_k(["LAB_RESULT", "LAB_RESULT"], {"LAB_RESULT"}, 5), 1.0)

    def test_zero_precision(self):
        self.assertEqual(precision_at_k(["VITAL_SIGN"], {"LAB_RESULT"}, 5), 0.0)

    def test_partial_precision(self):
        self.assertAlmostEqual(precision_at_k(["LAB_RESULT", "VITAL_SIGN"], {"LAB_RESULT"}, 2), 0.5)

    def test_perfect_recall(self):
        self.assertEqual(recall_at_k(["LAB_RESULT", "VITAL_SIGN"], {"LAB_RESULT", "VITAL_SIGN"}, 5), 1.0)

    def test_partial_recall(self):
        self.assertAlmostEqual(recall_at_k(["LAB_RESULT"], {"LAB_RESULT", "VITAL_SIGN"}, 5), 0.5)

    def test_empty_returned(self):
        self.assertEqual(precision_at_k([], {"LAB_RESULT"}, 5), 0.0)


class FixtureTests(unittest.TestCase):
    def test_fixtures_load_at_least_20(self):
        fixtures = load_fixtures()
        self.assertGreaterEqual(len(fixtures), 20)

    def test_every_fixture_has_required_fields(self):
        for fix in load_fixtures():
            self.assertIn("query", fix)
            self.assertIn("expected_event_types", fix)
            self.assertIsInstance(fix["expected_event_types"], list)

    def test_evaluate_fixture_returns_result(self):
        fix = {"query": "test", "expected_event_types": ["LAB_RESULT"]}
        result = evaluate_fixture(fix, ["LAB_RESULT", "VITAL_SIGN"], k=5)
        self.assertEqual(result.precision_at_k, 0.5)
        self.assertEqual(result.recall_at_k, 1.0)

    def test_score_all_returns_aggregates(self):
        fixtures = [
            {"query": "q1", "expected_event_types": ["LAB_RESULT"]},
            {"query": "q2", "expected_event_types": ["VITAL_SIGN"]},
        ]
        results = {
            "q1": ["LAB_RESULT"],
            "q2": ["VITAL_SIGN", "LAB_RESULT"],
        }
        scores = score_all(fixtures, results, k=5)
        self.assertGreaterEqual(scores["mean_precision_at_k"], 0.5)
        self.assertEqual(scores["mean_recall_at_k"], 1.0)


class GroundingTests(unittest.TestCase):
    def test_grounded_answer_scores_well(self):
        answer = "The patient has elevated potassium at 6.2 mmol/L suggesting hyperkalemia. Clinical review recommended."
        context = ["Patient potassium level 6.2 mmol/L abnormal elevated hyperkalemia"]
        score = score_grounding(answer, context)
        self.assertLessEqual(score.unsupported_claim_rate, 0.5)
        self.assertTrue(score.has_safety_caveat)

    def test_ungrounded_answer_scores_poorly(self):
        answer = "The weather is nice today. I recommend going for a walk in the park."
        context = ["Patient potassium level 6.2 mmol/L abnormal"]
        score = score_grounding(answer, context)
        self.assertGreater(score.unsupported_claim_rate, 0.0)

    def test_safety_caveat_detected(self):
        answer = "Results suggest elevated glucose. This is not medical advice."
        score = score_grounding(answer, [])
        self.assertTrue(score.has_safety_caveat)

    def test_no_caveat_detected(self):
        answer = "The patient has diabetes."
        score = score_grounding(answer, [])
        self.assertFalse(score.has_safety_caveat)

    def test_empty_answer(self):
        score = score_grounding("", ["some context"])
        self.assertEqual(score.claim_count, 0)
        self.assertEqual(score.unsupported_claim_rate, 0.0)


class FusionRerankTests(unittest.TestCase):
    def test_higher_relevance_ranks_first(self):
        items = [
            {"event_id": "a", "score": 0.5, "patient_id": "p1"},
            {"event_id": "b", "score": 0.9, "patient_id": "p1"},
        ]
        result = fusion_rerank(items)
        self.assertEqual(result[0]["event_id"], "b")

    def test_graph_signal_boosts_known_patients(self):
        items = [
            {"event_id": "a", "score": 0.8, "patient_id": "p1"},
            {"event_id": "b", "score": 0.8, "patient_id": "p2"},
        ]
        result = fusion_rerank(items, graph_patient_ids={"p1"})
        self.assertEqual(result[0]["patient_id"], "p1")

    def test_deterministic_across_runs(self):
        items = [
            {"event_id": "a", "score": 0.7, "patient_id": "p1"},
            {"event_id": "b", "score": 0.7, "patient_id": "p1"},
            {"event_id": "c", "score": 0.7, "patient_id": "p1"},
        ]
        r1 = [i["event_id"] for i in fusion_rerank(items)]
        r2 = [i["event_id"] for i in fusion_rerank(items)]
        self.assertEqual(r1, r2)

    def test_empty_input(self):
        self.assertEqual(fusion_rerank([]), [])

    def test_recency_boosts_recent_events(self):
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        old_iso = "2020-01-01T00:00:00Z"
        items = [
            {"event_id": "old", "score": 0.8, "event_ts": old_iso, "patient_id": "p1"},
            {"event_id": "new", "score": 0.8, "event_ts": now_iso, "patient_id": "p1"},
        ]
        result = fusion_rerank(items)
        self.assertEqual(result[0]["event_id"], "new")


if __name__ == "__main__":
    unittest.main()
