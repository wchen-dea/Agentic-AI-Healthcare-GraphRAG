from __future__ import annotations

import json
from typing import Any, Callable

from app.ontology_loader import provenance_for_source_type
from app.reference_data import build_reference_data, update_reference_store
from app.rules_engine import evaluate_claims_outcome_rules, evaluate_lab_signal_rules
from app.storage import build_qdrant_payload, qdrant_point_id
from app.text_processing import clinical_text, stable_embedding
from qdrant_client.models import PointStruct


class HealthcareEventPipelineService:
    """Coordinates enrichment, normalization, and sink writes for incoming events."""

    def __init__(
        self,
        *,
        ontology: dict[str, Any],
        lab_signal_rules: list[dict[str, Any]],
        claims_outcome_rules: list[dict[str, Any]],
        qdrant,
        qdrant_collection: str,
        neo4j,
        reference_store: dict[str, dict[str, Any]],
        normalize_event_payload: Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], tuple[dict[str, Any], dict[str, Any]]],
        graph_writes,
    ):
        self.ontology = ontology
        self.lab_signal_rules = lab_signal_rules
        self.claims_outcome_rules = claims_outcome_rules
        self.qdrant = qdrant
        self.qdrant_collection = qdrant_collection
        self.neo4j = neo4j
        self.reference_store = reference_store
        self.normalize_event_payload = normalize_event_payload
        self.graph_writes = graph_writes

    def process_reference_event(self, topic: str, raw_value, deserialize_event: Callable[[str, Any], dict[str, Any]]) -> None:
        event = deserialize_event(topic, raw_value)
        payload = json.loads(event.get("payload_json", "{}"))
        update_reference_store(self.reference_store, topic, event, payload)
        print(f"Updated reference data from topic={topic}")

    def enrich_event(self, event: dict[str, Any], payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        reference_data = build_reference_data(self.reference_store, event, payload)
        payload["reference_data"] = reference_data
        event["enriched"] = True
        event["reference_hit_count"] = sum(1 for value in reference_data.values() if value is not None)
        return event, payload

    def process_event(self, raw_value, topic: str, deserialize_event: Callable[[str, Any], dict[str, Any]]) -> None:
        event = deserialize_event(topic, raw_value)
        payload = json.loads(event.get("payload_json", "{}"))
        event, payload = self.enrich_event(event, payload)
        event, payload = self.normalize_event_payload(event, payload, self.ontology)
        event["ontology_version"] = self.ontology.get("version")
        event["payload_json"] = json.dumps(payload)
        text = clinical_text(event)
        vector = stable_embedding(text)
        self.write_qdrant(event, payload, text, vector)
        self.write_neo4j(event, payload, text)
        print(
            f"Processed event_id={event['event_id']} type={event['event_type']} "
            f"patient={event.get('patient_id')} enrich_hits={event.get('reference_hit_count', 0)}"
        )

    def write_qdrant(self, event: dict[str, Any], payload: dict[str, Any], text: str, vector: list[float]) -> None:
        point_id = qdrant_point_id(event["event_id"])
        provenance = provenance_for_source_type(self.ontology, event.get("source_type"))
        self.qdrant.upsert(
            collection_name=self.qdrant_collection,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload=build_qdrant_payload(event, payload, text, provenance),
            )],
        )

    def write_neo4j(self, event: dict[str, Any], payload: dict[str, Any], text: str) -> None:
        with self.neo4j.session() as session:
            session.execute_write(self.graph_writes.merge_base_event, event, text)
            session.execute_write(self.graph_writes.merge_reference_context, event, payload)
            event_type = event["event_type"]
            if event_type == "CLINICAL_NOTE":
                session.execute_write(self.graph_writes.merge_clinical_note, event, payload)
                session.execute_write(self.graph_writes.merge_adverse_event_signal, event, payload)
                if payload.get("event_family") == "ALLERGY_INTOLERANCE":
                    session.execute_write(self.graph_writes.merge_allergy_adverse_event, event, payload)
            elif event_type == "LAB_RESULT":
                session.execute_write(self.graph_writes.merge_lab_result, event, payload)
                signals = evaluate_lab_signal_rules(self.lab_signal_rules, payload.get("lab_name"), payload.get("value"))
                session.execute_write(self.graph_writes.merge_lab_signals, event["event_id"], signals)
            elif event_type == "VITAL_SIGN":
                session.execute_write(self.graph_writes.merge_device_reading, event, payload)
            elif event_type == "MEDICATION_ORDER":
                session.execute_write(self.graph_writes.merge_medication_order, event, payload)
            elif event_type == "CLAIM_STATUS":
                claim_outcomes = evaluate_claims_outcome_rules(
                    self.claims_outcome_rules,
                    event_type=event_type,
                    claim_type=payload.get("claim_type"),
                    procedure_code=payload.get("procedure_code"),
                )
                session.execute_write(self.graph_writes.merge_claim, event, payload, claim_outcomes)

    def handle_topic_message(
        self,
        topic: str,
        raw_value,
        *,
        reference_topics: set[str],
        event_topics: set[str],
        deserialize_event: Callable[[str, Any], dict[str, Any]],
    ) -> str:
        if topic in reference_topics:
            self.process_reference_event(topic, raw_value, deserialize_event)
            return "reference"
        if topic in event_topics:
            self.process_event(raw_value, topic, deserialize_event)
            return "event"
        print(f"Skipped message from unknown topic={topic}")
        return "skipped"