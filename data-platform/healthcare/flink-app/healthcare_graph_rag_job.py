"""Healthcare GraphRAG streaming processor."""

import json
import os

import app.graph_writes as graph_writes
from app.graph_writes import (
    merge_adverse_event_signal,
    merge_allergy_adverse_event,
    merge_base_event,
    merge_claim,
    merge_clinical_note,
    merge_device_reading,
    merge_lab_result,
    merge_lab_signals,
    merge_medication_order,
    merge_reference_context,
)
from app.ontology_loader import (
    load_claims_outcome_rules,
    load_drug_safety_rules,
    load_lab_signal_rules,
    load_ontology_bundle,
)
from app.normalization import normalize_event_payload
from app.pipeline_service import HealthcareEventPipelineService
from app.runner import run_consumer_loop
from app.text_processing import VECTOR_SIZE
from confluent_kafka import Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "healthcare_events")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "healthcare123")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")

TOPICS = [
    "healthcare.ehr.events",
    "healthcare.lab.results",
    "healthcare.device.telemetry",
    "healthcare.pharmacy.orders",
    "healthcare.claims.events",
]

REFERENCE_TOPICS = [
    "healthcare.master.patients",
    "healthcare.master.providers",
    "healthcare.master.devices",
    "healthcare.master.medications",
    "healthcare.master.payers",
]

ALL_TOPICS = TOPICS + REFERENCE_TOPICS
TOPIC_SET = set(TOPICS)
REFERENCE_TOPIC_SET = set(REFERENCE_TOPICS)


class HealthcareGraphRagProcessor:
    def __init__(self):
        self.ontology = load_ontology_bundle()
        self.lab_signal_rules = load_lab_signal_rules(self.ontology)
        self.claims_outcome_rules = load_claims_outcome_rules(self.ontology)
        self.drug_safety_rules = load_drug_safety_rules(self.ontology)
        self.qdrant = QdrantClient(url=QDRANT_URL)
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if QDRANT_COLLECTION not in existing:
            self.qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
        self.neo4j = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.schema_registry = SchemaRegistryClient({"url": SCHEMA_REGISTRY_URL})
        self.avro_deserializer = AvroDeserializer(
            schema_registry_client=self.schema_registry,
            from_dict=lambda obj, ctx: obj,
        )
        self.reference_store = {
            "patients": {},
            "providers": {},
            "devices": {},
            "medications": {},
            "payers": {},
        }
        self.pipeline = HealthcareEventPipelineService(
            ontology=self.ontology,
            lab_signal_rules=self.lab_signal_rules,
            claims_outcome_rules=self.claims_outcome_rules,
            qdrant=self.qdrant,
            qdrant_collection=QDRANT_COLLECTION,
            neo4j=self.neo4j,
            reference_store=self.reference_store,
            normalize_event_payload=normalize_event_payload,
            graph_writes=graph_writes,
        )

    def close(self):
        self.neo4j.close()

    def deserialize_event(self, topic: str, raw_value):
        if isinstance(raw_value, str):
            return json.loads(raw_value)

        if isinstance(raw_value, bytearray):
            raw_value = bytes(raw_value)

        if isinstance(raw_value, bytes):
            if raw_value.startswith(b"{"):
                return json.loads(raw_value.decode("utf-8"))
            return self.avro_deserializer(
                raw_value,
                SerializationContext(topic, MessageField.VALUE),
            )

        raise TypeError(f"Unsupported raw value type: {type(raw_value)}")

    def process_reference_event(self, topic: str, raw_value):
        self.pipeline.process_reference_event(topic, raw_value, self.deserialize_event)

    def enrich_event(self, event: dict, payload: dict):
        return self.pipeline.enrich_event(event, payload)

    def process_event(self, raw_value, topic: str):
        self.pipeline.process_event(raw_value, topic, self.deserialize_event)

    def write_qdrant(self, event, payload, text, vector):
        self.pipeline.write_qdrant(event, payload, text, vector)

    def write_neo4j(self, event, payload, text):
        self.pipeline.write_neo4j(event, payload, text)

    def handle_topic_message(self, topic: str, raw_value) -> str:
        return self.pipeline.handle_topic_message(
            topic,
            raw_value,
            reference_topics=REFERENCE_TOPIC_SET,
            event_topics=TOPIC_SET,
            deserialize_event=self.deserialize_event,
        )

    merge_base_event = staticmethod(merge_base_event)
    merge_reference_context = staticmethod(merge_reference_context)
    merge_clinical_note = staticmethod(merge_clinical_note)
    merge_lab_result = staticmethod(merge_lab_result)
    merge_lab_signals = staticmethod(merge_lab_signals)
    merge_device_reading = staticmethod(merge_device_reading)
    merge_medication_order = staticmethod(merge_medication_order)
    merge_claim = staticmethod(merge_claim)
    merge_adverse_event_signal = staticmethod(merge_adverse_event_signal)
    merge_allergy_adverse_event = staticmethod(merge_allergy_adverse_event)


def main():
    c = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": "healthcare-graphrag-processor",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    c.subscribe(ALL_TOPICS)
    processor = HealthcareGraphRagProcessor()
    print(f"Subscribed to topics: {ALL_TOPICS}")
    try:
        run_consumer_loop(c, processor, kafka_exception_cls=KafkaException)
    finally:
        processor.close()
        c.close()


if __name__ == "__main__":
    main()
