from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

from httpx import Headers
from neo4j import Query
from qdrant_client.http.exceptions import UnexpectedResponse

from healthcare_agent.retrieval import search as search_module
from healthcare_agent.retrieval.search import classify_query_domains, graph_search, vector_search


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

    def test_falls_back_to_unnamed_vector_on_schema_error(self):
        schema_error = UnexpectedResponse(400, "Bad Request", b"Wrong vector name", Headers())
        client = self._mock_qdrant([schema_error, [self._make_hit("e1", 0.9)]])

        results = vector_search(client, "coll", "diagnosis?", None, limit=5)

        self.assertEqual([r["event_id"] for r in results], ["e1"])
        self.assertIsInstance(client.search.call_args_list[1].kwargs["query_vector"], list)

    def test_transport_errors_are_not_masked_by_fallback(self):
        client = self._mock_qdrant([ConnectionError("qdrant down")])

        with self.assertRaises(ConnectionError):
            vector_search(client, "coll", "diagnosis?", None, limit=5)
        self.assertEqual(client.search.call_count, 1)

    def test_server_errors_are_not_masked_by_fallback(self):
        client = self._mock_qdrant([UnexpectedResponse(503, "Unavailable", b"", Headers())])

        with self.assertRaises(UnexpectedResponse):
            vector_search(client, "coll", "diagnosis?", None, limit=5)


class GraphSearchTests(unittest.TestCase):
    def _driver(self, records):
        session = MagicMock()
        session.run.return_value = records
        driver = MagicMock()
        driver.session.return_value.__enter__.return_value = session
        return driver, session

    def test_uses_query_timeout_and_dedupes_patient_ids(self):
        driver, session = self._driver([{"patient_id": "p-1"}])

        results = graph_search(driver, ["p-1", "p-1", "", "p-2"])

        query, params = session.run.call_args.args
        self.assertIsInstance(query, Query)
        self.assertEqual(query.timeout, search_module.graph_query_timeout_seconds)
        self.assertEqual(params["patient_ids"], ["p-1", "p-2"])
        self.assertEqual(results, [{"patient_id": "p-1"}])

    def test_caps_patient_ids(self):
        driver, session = self._driver([])
        ids = [f"p-{i}" for i in range(search_module.max_graph_patient_ids + 10)]

        graph_search(driver, ids)

        self.assertEqual(len(session.run.call_args.args[1]["patient_ids"]), search_module.max_graph_patient_ids)

    def test_empty_patient_ids_skips_neo4j(self):
        driver, session = self._driver([])

        self.assertEqual(graph_search(driver, []), [])
        session.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
