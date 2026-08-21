from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import helpers  # noqa: F401

from app.pipeline_service import HealthcareEventPipelineService


class _SessionRecorder:
    def __init__(self):
        self.calls: list[tuple[object, tuple[object, ...]]] = []

    def execute_write(self, func, *args):
        self.calls.append((func, args))


class _SessionContext:
    def __init__(self, session):
        self.session = session

    def __enter__(self):
        return self.session

    def __exit__(self, exc_type, exc, tb):
        return False


class PipelineServiceTests(unittest.TestCase):
    def _make_service(self):
        graph_writes = SimpleNamespace(
            merge_base_event=lambda *args: None,
            merge_reference_context=lambda *args: None,
            merge_clinical_note=lambda *args: None,
            merge_lab_result=lambda *args: None,
            merge_lab_signals=lambda *args: None,
            merge_device_reading=lambda *args: None,
            merge_medication_order=lambda *args: None,
            merge_claim=lambda *args: None,
            merge_adverse_event_signal=lambda *args: None,
        )
        qdrant = Mock()
        neo4j = Mock()
        return HealthcareEventPipelineService(
            ontology={"version": "0.1.0"},
            lab_signal_rules=[{"rule_id": "lab-1"}],
            claims_outcome_rules=[{"rule_id": "claim-1"}],
            qdrant=qdrant,
            qdrant_collection="healthcare_events",
            neo4j=neo4j,
            reference_store={"patients": {}, "providers": {}, "devices": {}, "medications": {}, "payers": {}},
            normalize_event_payload=lambda event, payload, ontology: (event, payload),
            graph_writes=graph_writes,
        )

    def test_handle_topic_message_routes_reference_topics(self):
        svc = self._make_service()
        svc.process_reference_event = Mock()
        svc.process_event = Mock()

        result = svc.handle_topic_message(
            "healthcare.master.patients",
            b"{}",
            reference_topics={"healthcare.master.patients"},
            event_topics={"healthcare.ehr.events"},
            deserialize_event=lambda topic, raw: {},
        )

        self.assertEqual(result, "reference")
        svc.process_reference_event.assert_called_once()
        svc.process_event.assert_not_called()

    def test_handle_topic_message_routes_event_topics(self):
        svc = self._make_service()
        svc.process_reference_event = Mock()
        svc.process_event = Mock()

        result = svc.handle_topic_message(
            "healthcare.ehr.events",
            b"{}",
            reference_topics={"healthcare.master.patients"},
            event_topics={"healthcare.ehr.events"},
            deserialize_event=lambda topic, raw: {},
        )

        self.assertEqual(result, "event")
        svc.process_event.assert_called_once()
        svc.process_reference_event.assert_not_called()

    def test_handle_topic_message_skips_unknown_topic(self):
        svc = self._make_service()
        svc.process_reference_event = Mock()
        svc.process_event = Mock()

        result = svc.handle_topic_message(
            "unknown.topic",
            b"{}",
            reference_topics={"healthcare.master.patients"},
            event_topics={"healthcare.ehr.events"},
            deserialize_event=lambda topic, raw: {},
        )

        self.assertEqual(result, "skipped")
        svc.process_event.assert_not_called()
        svc.process_reference_event.assert_not_called()

    def test_write_qdrant_dispatches_point_upsert(self):
        svc = self._make_service()
        event = {
            "event_id": "evt-1",
            "event_ts": "2026-08-12T00:00:00Z",
            "event_type": "LAB_RESULT",
            "source_type": "LAB",
        }
        payload = {"lab_name": "Potassium", "value": 5.8}

        with patch("app.pipeline_service.qdrant_point_id", return_value=101), patch(
            "app.pipeline_service.provenance_for_source_type",
            return_value={"trust_level": "high", "phi_class": "phi_limited", "retention_class": "regulated"},
        ), patch(
            "app.pipeline_service.build_qdrant_payload",
            return_value={"event_id": "evt-1"},
        ), patch("app.pipeline_service.PointStruct", side_effect=lambda **kwargs: kwargs):
            svc.write_qdrant(event, payload, "Potassium 5.8", [0.1, 0.2])

        svc.qdrant.upsert.assert_called_once()
        kwargs = svc.qdrant.upsert.call_args.kwargs
        self.assertEqual(kwargs["collection_name"], "healthcare_events")
        self.assertEqual(kwargs["points"][0]["id"], 101)
        self.assertEqual(kwargs["points"][0]["payload"], {"event_id": "evt-1"})

    def test_write_neo4j_dispatches_lab_result_signal_path(self):
        svc = self._make_service()
        session = _SessionRecorder()
        svc.neo4j.session.return_value = _SessionContext(session)
        event = {"event_id": "evt-1", "event_type": "LAB_RESULT"}
        payload = {"lab_name": "Potassium", "value": 5.8}

        with patch(
            "app.pipeline_service.evaluate_lab_signal_rules",
            return_value=[{"rule_id": "potassium_hyperkalemia", "condition": "Hyperkalemia", "reason": "elevated_potassium"}],
        ):
            svc.write_neo4j(event, payload, "text")

        funcs = [call[0] for call in session.calls]
        self.assertEqual(funcs[0], svc.graph_writes.merge_base_event)
        self.assertEqual(funcs[1], svc.graph_writes.merge_reference_context)
        self.assertIn(svc.graph_writes.merge_lab_result, funcs)
        self.assertIn(svc.graph_writes.merge_lab_signals, funcs)
        lab_signal_call = [call for call in session.calls if call[0] is svc.graph_writes.merge_lab_signals][0]
        self.assertEqual(lab_signal_call[1][0], "evt-1")

    def test_write_neo4j_dispatches_claim_path_with_outcomes(self):
        svc = self._make_service()
        session = _SessionRecorder()
        svc.neo4j.session.return_value = _SessionContext(session)
        event = {"event_id": "evt-2", "event_type": "CLAIM_STATUS"}
        payload = {"claim_type": "institutional", "procedure_code": "99291"}

        with patch(
            "app.pipeline_service.evaluate_claims_outcome_rules",
            return_value=[{"rule_id": "institutional_claim_hospitalization", "adverse_outcome": "HO"}],
        ):
            svc.write_neo4j(event, payload, "text")

        claim_call = [call for call in session.calls if call[0] is svc.graph_writes.merge_claim][0]
        self.assertEqual(claim_call[1][0], event)
        self.assertEqual(claim_call[1][1], payload)
        self.assertEqual(claim_call[1][2][0]["adverse_outcome"], "HO")
