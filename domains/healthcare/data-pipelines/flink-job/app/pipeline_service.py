from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

from qdrant_client.models import PointStruct

from app.ontology_loader import provenance_for_source_type
from app.reference_data import build_reference_data, update_reference_store
from app.rules_engine import evaluate_claims_outcome_rules, evaluate_lab_signal_rules
from app.storage import build_qdrant_payload, qdrant_point_id
from app.text_processing import clinical_text, domain_for_event_type, stable_embedding
from app.qdrant_outbox import QdrantOutbox


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
        reconciliation_path: str | None = None,
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
        self.reconciliation_path = Path(
            reconciliation_path
            or os.getenv("QDRANT_OUTBOX_PATH", "/var/lib/flink/qdrant-outbox.sqlite3")
        )
        self.outbox = None if self.reconciliation_path.suffix == ".jsonl" else QdrantOutbox(str(self.reconciliation_path))

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
        domain = domain_for_event_type(event["event_type"])
        vector = stable_embedding(text, domain=domain)
        # Neo4j first (one transaction), then Qdrant. Both sinks are idempotent
        # (MERGE / deterministic point id), so a replay after a partial failure
        # converges instead of leaving vectors without graph context.
        self.write_neo4j(event, payload, text)
        item = {"event": event, "payload": payload, "text": text, "vector": vector, "domain": domain}
        task_id = self._enqueue_reconciliation(item) if self.outbox is not None else None
        try:
            self.write_qdrant(event, payload, text, vector, domain)
            if task_id is not None:
                self._ack_reconciliation(task_id)
        except Exception:
            if self.outbox is None:
                self._record_reconciliation(event, payload, text, vector, domain)
            raise
        print(
            f"Processed event_id={event['event_id']} type={event['event_type']} "
            f"patient={event.get('patient_id')} enrich_hits={event.get('reference_hit_count', 0)}"
        )

    def write_qdrant(self, event: dict[str, Any], payload: dict[str, Any], text: str, vector: list[float], domain: str) -> None:
        point_id = qdrant_point_id(event["event_id"])
        provenance = provenance_for_source_type(self.ontology, event.get("source_type"))
        qdrant_payload = build_qdrant_payload(event, payload, text, provenance)
        qdrant_payload["embedding_domain"] = domain
        self.qdrant.upsert(
            collection_name=self.qdrant_collection,
            points=[PointStruct(
                id=point_id,
                vector={domain: vector},
                payload=qdrant_payload,
            )],
        )

    def _record_reconciliation(
        self, event: dict[str, Any], payload: dict[str, Any], text: str, vector: list[float], domain: str
    ) -> None:
        """Persist a replayable Qdrant operation after a successful graph write."""
        record = {"event": event, "payload": payload, "text": text, "vector": vector, "domain": domain}
        if self.outbox is not None:
            self._enqueue_reconciliation(record)
        else:
            self.reconciliation_path.parent.mkdir(parents=True, exist_ok=True)
            with self.reconciliation_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")

    def _enqueue_reconciliation(self, record: dict[str, Any]) -> str:
        if self.reconciliation_path.suffix == ".jsonl":
            self.reconciliation_path.parent.mkdir(parents=True, exist_ok=True)
            with self.reconciliation_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, separators=(",", ":")) + "\n")
            return record["event"]["event_id"]
        if self.outbox is None:
            raise RuntimeError("SQLite outbox is disabled for JSONL compatibility mode")
        return self.outbox.enqueue(record)

    def _ack_reconciliation(self, task_id: str) -> None:
        if self.reconciliation_path.suffix != ".jsonl":
            assert self.outbox is not None
            self.outbox.acknowledge(task_id)

    def _replay_outbox(self) -> int:
        replayed = 0
        while True:
            assert self.outbox is not None
            item = self.outbox.claim()
            if item is None:
                return replayed
            task_id = item.pop("_task_id")
            try:
                self.write_qdrant(item["event"], item["payload"], item["text"], item["vector"], item["domain"])
            except Exception as exc:
                self.outbox.fail(task_id, exc)
                continue
            self.outbox.acknowledge(task_id)
            replayed += 1

    def _replay_jsonl(self) -> int:
        self.reconciliation_path.parent.mkdir(parents=True, exist_ok=True)
        """Replay queued Qdrant writes and retain only failures."""
        if not self.reconciliation_path.exists():
            return 0
        pending = [json.loads(line) for line in self.reconciliation_path.read_text(encoding="utf-8").splitlines() if line]
        failed: list[dict[str, Any]] = []
        for item in pending:
            try:
                self.write_qdrant(item["event"], item["payload"], item["text"], item["vector"], item["domain"])
            except Exception:
                failed.append(item)
        if failed:
            self.reconciliation_path.write_text(
                "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in failed), encoding="utf-8"
            )
        else:
            self.reconciliation_path.unlink()
        return len(pending) - len(failed)

    def replay_reconciliation(self) -> int:
        """Replay durable Qdrant tasks; SQLite is concurrency-safe and default."""
        if self.reconciliation_path.suffix != ".jsonl":
            return self._replay_outbox()
        return self._replay_jsonl()

    def write_neo4j(self, event: dict[str, Any], payload: dict[str, Any], text: str) -> None:
        operations = self._neo4j_operations(event, payload, text)

        def _apply(tx) -> None:
            for func, args in operations:
                func(tx, *args)

        with self.neo4j.session() as session:
            session.execute_write(_apply)

    def _neo4j_operations(
        self, event: dict[str, Any], payload: dict[str, Any], text: str
    ) -> list[tuple[Callable[..., Any], tuple[Any, ...]]]:
        gw = self.graph_writes
        ops: list[tuple[Callable[..., Any], tuple[Any, ...]]] = [
            (gw.merge_base_event, (event, text)),
            (gw.merge_reference_context, (event, payload)),
        ]
        event_type = event["event_type"]
        if event_type == "CLINICAL_NOTE":
            ops.append((gw.merge_clinical_note, (event, payload)))
            ops.append((gw.merge_adverse_event_signal, (event, payload)))
            if payload.get("event_family") == "ALLERGY_INTOLERANCE":
                ops.append((gw.merge_allergy_adverse_event, (event, payload)))
        elif event_type == "LAB_RESULT":
            ops.append((gw.merge_lab_result, (event, payload)))
            signals = evaluate_lab_signal_rules(self.lab_signal_rules, payload.get("lab_name"), payload.get("value"))
            ops.append((gw.merge_lab_signals, (event["event_id"], signals)))
        elif event_type == "VITAL_SIGN":
            ops.append((gw.merge_device_reading, (event, payload)))
        elif event_type == "MEDICATION_ORDER":
            ops.append((gw.merge_medication_order, (event, payload)))
        elif event_type == "CLAIM_STATUS":
            claim_outcomes = evaluate_claims_outcome_rules(
                self.claims_outcome_rules,
                event_type=event_type,
                claim_type=payload.get("claim_type"),
                procedure_code=payload.get("procedure_code"),
            )
            ops.append((gw.merge_claim, (event, payload, claim_outcomes)))
        return ops

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