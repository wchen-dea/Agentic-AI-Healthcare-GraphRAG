from __future__ import annotations

import unittest

import helpers  # noqa: F401

from app.storage import build_qdrant_payload, qdrant_point_id


class StorageTests(unittest.TestCase):
    def test_qdrant_point_id_is_stable_for_same_event_id(self):
        event_id = "evt-123"
        first = qdrant_point_id(event_id)
        second = qdrant_point_id(event_id)

        self.assertIsInstance(first, int)
        self.assertEqual(first, second)

    def test_qdrant_point_id_changes_for_different_event_ids(self):
        self.assertNotEqual(qdrant_point_id("evt-1"), qdrant_point_id("evt-2"))

    def test_build_qdrant_payload_applies_defaults_and_provenance(self):
        event = {
            "event_id": "evt-1",
            "event_ts": "2026-08-12T00:00:00Z",
            "event_type": "LAB_RESULT",
            "patient_id": "patient-1",
            "source_system": "epic",
            "source_type": "LAB",
            "ontology_version": "0.1.0",
        }
        payload = {"lab_name": "Potassium", "value": 5.8}
        provenance = {
            "trust_level": "high",
            "phi_class": "phi_limited",
            "retention_class": "regulated",
        }

        qdrant_payload = build_qdrant_payload(event, payload, "Potassium 5.8", provenance)

        self.assertEqual(qdrant_payload["event_id"], "evt-1")
        self.assertFalse(qdrant_payload["enriched"])
        self.assertEqual(qdrant_payload["reference_hit_count"], 0)
        self.assertEqual(qdrant_payload["trust_level"], "high")
        self.assertEqual(qdrant_payload["phi_class"], "phi_limited")
        self.assertEqual(qdrant_payload["retention_class"], "regulated")
        self.assertEqual(qdrant_payload["payload"], payload)

    def test_build_qdrant_payload_preserves_enrichment_fields_when_present(self):
        event = {
            "event_id": "evt-2",
            "event_ts": "2026-08-12T00:00:00Z",
            "event_type": "CLINICAL_NOTE",
            "patient_id": "patient-2",
            "source_system": "cerner",
            "source_type": "EHR",
            "enriched": True,
            "reference_hit_count": 3,
            "ontology_version": "0.2.0",
        }

        qdrant_payload = build_qdrant_payload(event, {"symptom": "cough"}, "Patient has cough", {})

        self.assertTrue(qdrant_payload["enriched"])
        self.assertEqual(qdrant_payload["reference_hit_count"], 3)
        self.assertEqual(qdrant_payload["event_type"], "CLINICAL_NOTE")
