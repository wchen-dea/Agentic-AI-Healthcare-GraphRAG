"""Supply Chain GraphRAG streaming processor."""

import json
import os

from app.graph_writes import (
    merge_base_event,
    merge_disruption_alert,
    merge_facility_reference,
    merge_inventory_level,
    merge_part_reference,
    merge_purchase_order,
    merge_quality_result,
    merge_shipment,
    merge_supplier_reference,
)
from app.pipeline_service import SupplyChainPipelineService, clinical_text
from confluent_kafka import Consumer, KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import MessageField, SerializationContext
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

try:
    from platform.embedding import stable_embedding, VECTOR_SIZE
except ImportError:
    from app.pipeline_service import _md5_embedding as stable_embedding
    VECTOR_SIZE = 384

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

EVENT_TYPE_HANDLER = {
    "PURCHASE_ORDER": merge_purchase_order,
    "SHIPMENT_UPDATE": merge_shipment,
    "QUALITY_RESULT": merge_quality_result,
    "DISRUPTION_ALERT": merge_disruption_alert,
    "INVENTORY_LEVEL": merge_inventory_level,
}

REFERENCE_TYPE_HANDLER = {
    "SUPPLIER_MASTER_UPSERT": merge_supplier_reference,
    "PART_MASTER_UPSERT": merge_part_reference,
    "FACILITY_MASTER_UPSERT": merge_facility_reference,
}


def _embed(text: str) -> list[float]:
    try:
        return stable_embedding(text)
    except Exception:
        import hashlib
        vec = [0.0] * VECTOR_SIZE
        for token in text.lower().split():
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % VECTOR_SIZE] += 1.0
        norm = sum(x * x for x in vec) ** 0.5
        return [x / norm if norm else 0.0 for x in vec]


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

        text = clinical_text(event)
        vector = _embed(text)

        self.pipeline._write_qdrant(event, payload, text, vector)

        with self.neo4j.session() as session:
            session.execute_write(merge_base_event, event, text)
            handler = EVENT_TYPE_HANDLER.get(event_type)
            if handler:
                session.execute_write(handler, event, payload)

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
                import time
                time.sleep(1)
    finally:
        processor.close()
        c.close()


if __name__ == "__main__":
    main()
