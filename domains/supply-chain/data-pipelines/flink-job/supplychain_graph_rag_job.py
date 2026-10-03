"""Supply Chain GraphRAG streaming processor."""

import hashlib
import json
import os
import time

from app.graph_writes import (
    merge_facility_reference,
    merge_part_reference,
    merge_supplier_reference,
)
from app.pipeline_service import SupplyChainPipelineService
from confluent_kafka import Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

_PROVIDER_DEFAULT_DIMS = {"local": 384, "databricks": 1024}


def _configured_vector_size() -> int:
    """Mirror knowledge_core.get_vector_size() for runs without knowledge_core."""
    override = os.getenv("EMBEDDING_DIM", "").strip()
    if override:
        return int(override)
    provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower() or "local"
    return _PROVIDER_DEFAULT_DIMS.get(provider, 384)


VECTOR_SIZE = _configured_vector_size()


def _md5_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    """Deterministic bag-of-words vector; matches knowledge_core's fallback."""
    vec = [0.0] * dim
    for token in text.lower().split():
        vec[int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def _require_model() -> bool:
    return os.getenv("EMBEDDING_REQUIRE_MODEL", "").strip().lower() in {"1", "true", "yes", "on"}


try:
    from knowledge_core.embedding import VECTOR_SIZE, stable_embedding
except ImportError:
    if _require_model():
        raise
    stable_embedding = _md5_embedding

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant-sc:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "supplychain_events")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j-sc:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "supplychain123")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://schema-registry:8081")

TOPICS = [
    "supplychain.purchase.orders",
    "supplychain.shipment.updates",
    "supplychain.quality.results",
    "supplychain.disruption.alerts",
    "supplychain.inventory.levels",
]

REFERENCE_TOPICS = [
    "supplychain.master.suppliers",
    "supplychain.master.parts",
    "supplychain.master.facilities",
]

ALL_TOPICS = TOPICS + REFERENCE_TOPICS
TOPIC_SET = set(TOPICS)
REFERENCE_TOPIC_SET = set(REFERENCE_TOPICS)

REFERENCE_TYPE_HANDLER = {
    "SUPPLIER_MASTER_UPSERT": merge_supplier_reference,
    "PART_MASTER_UPSERT": merge_part_reference,
    "FACILITY_MASTER_UPSERT": merge_facility_reference,
}


def _embed(text: str) -> list[float]:
    try:
        return stable_embedding(text, VECTOR_SIZE)
    except Exception:
        # Strict mode: never mix MD5 vectors into a collection queried with the model.
        if _require_model():
            raise
        return _md5_embedding(text, VECTOR_SIZE)


class SupplyChainProcessor:
    def __init__(self):
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
        self.pipeline = SupplyChainPipelineService(
            neo4j_driver=self.neo4j,
            qdrant_client=self.qdrant,
            qdrant_collection=QDRANT_COLLECTION,
            embed_fn=_embed,
        )

    def close(self):
        self.neo4j.close()

    def deserialize(self, topic: str, raw_value):
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
        raise TypeError(f"Unsupported value type: {type(raw_value)}")

    def handle_topic_message(self, topic: str, raw_value) -> str:
        event = self.deserialize(topic, raw_value)
        payload = json.loads(event.get("payload_json", "{}"))
        event_type = event.get("event_type", "")

        if topic in REFERENCE_TOPIC_SET:
            handler = REFERENCE_TYPE_HANDLER.get(event_type)
            if handler:
                with self.neo4j.session() as session:
                    session.execute_write(handler, event, payload)
            return f"REF:{event_type}"

        self.pipeline.process_event(event)

        print(f"Processed {event_type} event {event.get('event_id', '?')}")
        return f"OK:{event_type}"


def main():
    c = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP,
        "group.id": "supplychain-graphrag-processor",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    c.subscribe(ALL_TOPICS)
    processor = SupplyChainProcessor()
    print(f"Supply-chain processor subscribed to: {ALL_TOPICS}")
    try:
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            try:
                processor.handle_topic_message(msg.topic(), msg.value())
                c.commit(msg, asynchronous=False)
            except Exception as ex:
                print(f"FAILED key={msg.key()} error={ex}")
                time.sleep(1)
    finally:
        processor.close()
        c.close()


if __name__ == "__main__":
    main()
