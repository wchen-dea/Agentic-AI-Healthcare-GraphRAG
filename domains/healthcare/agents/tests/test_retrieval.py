from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.retrieval import classify_query_domains, vector_search


class ClassifyQueryDomainsTests(unittest.TestCase):
    def test_clinical_question_returns_clinical_first(self):
        domains = classify_query_domains("What medications does the patient take?")
        self.assertEqual(domains[0], "clinical")

    def test_claims_question_returns_claims(self):
        domains = classify_query_domains("Was the insurance claim denied?")
        self.assertIn("claims", domains)

    def test_vitals_question_returns_device(self):
        domains = classify_query_domains("What is the patient heart rate?")
        self.assertIn("device", domains)

    def test_mixed_claims_clinical_returns_both(self):
        domains = classify_query_domains("What diagnosis led to the denied claim?")
        self.assertIn("claims", domains)
        self.assertIn("clinical", domains)

    def test_generic_question_defaults_to_clinical(self):
        domains = classify_query_domains("Tell me about this patient")
        self.assertEqual(domains, ["clinical"])

    def test_spo2_routes_to_device(self):
        domains = classify_query_domains("Is the SpO2 level normal?")
        self.assertIn("device", domains)

    def test_payer_routes_to_claims(self):
        domains = classify_query_domains("Which payer covers this procedure?")
        self.assertIn("claims", domains)

    def test_blood_pressure_routes_to_device(self):
        domains = classify_query_domains("What is the blood pressure trend?")
        self.assertIn("device", domains)


class VectorSearchMultiDomainTests(unittest.TestCase):
    def _mock_qdrant(self, hits_per_call):
        client = Mock()
        client.search.side_effect = hits_per_call
        return client

    def _make_hit(self, event_id, score, event_type="LAB_RESULT", domain="clinical"):
        return SimpleNamespace(
            score=score,
            payload={
                "event_id": event_id,
                "patient_id": "p-1",
                "event_type": event_type,
                "text": f"text for {event_id}",
                "embedding_domain": domain,
            },
        )

    def test_search_returns_results_sorted_by_score(self):
        clinical_hits = [self._make_hit("e1", 0.9), self._make_hit("e2", 0.7)]
        client = self._mock_qdrant([clinical_hits])

        results = vector_search(client, "coll", "diagnosis?", "p-1", limit=5)

        self.assertGreaterEqual(results[0]["score"], results[-1]["score"])

    def test_search_deduplicates_across_domains(self):
        clinical_hits = [self._make_hit("e1", 0.9)]
        claims_hits = [self._make_hit("e1", 0.8, "CLAIM_STATUS", "claims")]
        client = self._mock_qdrant([clinical_hits, claims_hits])

        results = vector_search(client, "coll", "claim denied for diagnosis", "p-1", limit=5)

        event_ids = [r["event_id"] for r in results]
        self.assertEqual(len(event_ids), len(set(event_ids)))

    def test_search_respects_limit(self):
        hits = [self._make_hit(f"e{i}", 0.9 - i * 0.1) for i in range(10)]
        client = self._mock_qdrant([hits])

        results = vector_search(client, "coll", "patient status", None, limit=3)

        self.assertLessEqual(len(results), 3)

    def test_embedding_domain_field_in_results(self):
        device_hits = [self._make_hit("e1", 0.9, "VITAL_SIGN", "device")]
        clinical_hits = []
        client = self._mock_qdrant([clinical_hits, device_hits])

        results = vector_search(client, "coll", "heart rate", None, limit=5)

        self.assertEqual(results[0]["embedding_domain"], "device")


if __name__ == "__main__":
    unittest.main()
