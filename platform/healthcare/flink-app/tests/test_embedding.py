from __future__ import annotations

import unittest

import helpers  # noqa: F401

from shared.embedding import (
    ALL_DOMAINS,
    VECTOR_SIZE,
    domain_for_event_type,
    stable_embedding,
)


class DomainMappingTests(unittest.TestCase):
    def test_clinical_note_maps_to_clinical(self):
        self.assertEqual(domain_for_event_type("CLINICAL_NOTE"), "clinical")

    def test_lab_result_maps_to_clinical(self):
        self.assertEqual(domain_for_event_type("LAB_RESULT"), "clinical")

    def test_medication_order_maps_to_clinical(self):
        self.assertEqual(domain_for_event_type("MEDICATION_ORDER"), "clinical")

    def test_vital_sign_maps_to_device(self):
        self.assertEqual(domain_for_event_type("VITAL_SIGN"), "device")

    def test_claim_status_maps_to_claims(self):
        self.assertEqual(domain_for_event_type("CLAIM_STATUS"), "claims")

    def test_unknown_type_defaults_to_clinical(self):
        self.assertEqual(domain_for_event_type("UNKNOWN_TYPE"), "clinical")

    def test_all_domains_has_three_entries(self):
        self.assertEqual(set(ALL_DOMAINS), {"clinical", "claims", "device"})


class StableEmbeddingTests(unittest.TestCase):
    def test_returns_correct_dimension(self):
        vec = stable_embedding("test text", domain="clinical")
        self.assertEqual(len(vec), VECTOR_SIZE)

    def test_different_text_gives_different_vectors(self):
        v1 = stable_embedding("clinical diagnosis note", domain="clinical")
        v2 = stable_embedding("insurance claim denied", domain="claims")
        self.assertNotEqual(v1, v2)

    def test_same_text_same_domain_is_deterministic(self):
        v1 = stable_embedding("heart rate 80 bpm", domain="device")
        v2 = stable_embedding("heart rate 80 bpm", domain="device")
        self.assertEqual(v1, v2)

    def test_all_domains_produce_valid_vectors(self):
        for domain in ALL_DOMAINS:
            vec = stable_embedding("sample text", domain=domain)
            self.assertEqual(len(vec), VECTOR_SIZE)
            self.assertTrue(all(isinstance(v, float) for v in vec))


if __name__ == "__main__":
    unittest.main()
