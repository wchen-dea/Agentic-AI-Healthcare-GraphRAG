"""
Healthcare GraphRAG streaming processor.

For local MVP reliability this script runs inside the Flink application container and uses
Kafka consumer APIs directly while applying Flink-style streaming design principles:
continuous consumption, idempotent sinks, replay-safe event IDs, and graph/vector dual writes.

To convert to a native PyFlink DataStream job, keep the same process_event(), write_qdrant(),
and write_neo4j() functions and replace the KafkaConsumer loop with KafkaSource + sink function.
"""

import hashlib
import json
import os
import time

from confluent_kafka import Consumer, KafkaException
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "healthcare_events")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "healthcare123")

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

VECTOR_SIZE = 384


def stable_embedding(text: str, dim: int = VECTOR_SIZE):
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def clinical_text(event: dict) -> str:
    payload = json.loads(event.get("payload_json", "{}"))
    event_type = event.get("event_type")
    reference = payload.get("reference_data", {})

    ref_parts = []
    patient_ref = reference.get("patient")
    provider_ref = reference.get("provider")
    device_ref = reference.get("device")
    medication_ref = reference.get("medication")
    payer_ref = reference.get("payer")

    if patient_ref:
        ref_parts.append(
            f"Patient profile age {patient_ref.get('age')}, sex {patient_ref.get('sex')}, risk {patient_ref.get('risk_tier')}."
        )
    if provider_ref:
        ref_parts.append(
            f"Provider {provider_ref.get('name')} specialty {provider_ref.get('specialty')}."
        )
    if device_ref:
        ref_parts.append(
            f"Device model {device_ref.get('model')} vendor {device_ref.get('vendor')}."
        )
    if medication_ref:
        ref_parts.append(
            f"Medication class {medication_ref.get('drug_class')} safety tier {medication_ref.get('safety_tier')}."
        )
    if payer_ref:
        ref_parts.append(
            f"Payer plan {payer_ref.get('plan_type')} region {payer_ref.get('region')}."
        )

    ref_summary = " ".join([part for part in ref_parts if part and "None" not in part])

    if event_type == "CLINICAL_NOTE":
        return " ".join([item for item in [
            f"Patient {event['patient_id']} clinical note from {event['source_system']}. "
            f"Diagnosis {payload.get('diagnosis')}. Symptom {payload.get('symptom')}. "
            f"Note: {payload.get('note')}",
            ref_summary,
        ] if item])
    if event_type == "LAB_RESULT":
        return " ".join([item for item in [
            f"Patient {event['patient_id']} lab result. "
            f"{payload.get('lab_name')} equals {payload.get('value')} {payload.get('unit')}. "
            f"Abnormal: {payload.get('abnormal')}",
            ref_summary,
        ] if item])
    if event_type == "VITAL_SIGN":
        return " ".join([item for item in [
            f"Patient {event['patient_id']} device telemetry. "
            f"Heart rate {payload.get('heart_rate')}, SpO2 {payload.get('spo2')}, "
            f"blood pressure {payload.get('systolic_bp')}/{payload.get('diastolic_bp')}.",
            ref_summary,
        ] if item])
    if event_type == "MEDICATION_ORDER":
        return " ".join([item for item in [
            f"Patient {event['patient_id']} medication order. "
            f"Medication {payload.get('medication')} dose {payload.get('dose')} "
            f"route {payload.get('route')} frequency {payload.get('frequency')}.",
            ref_summary,
        ] if item])
    if event_type == "CLAIM_STATUS":
        return " ".join([item for item in [
            f"Patient {event['patient_id']} claim event. "
            f"Payer {payload.get('payer')} procedure {payload.get('procedure_code')} "
            f"status {payload.get('status')}.",
            ref_summary,
        ] if item])
    return json.dumps(event)


class HealthcareGraphRagProcessor:
    def __init__(self):
        self.qdrant = QdrantClient(url=QDRANT_URL)
        existing = [c.name for c in self.qdrant.get_collections().collections]
        if QDRANT_COLLECTION not in existing:
            self.qdrant.create_collection(
                collection_name=QDRANT_COLLECTION,
                vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
            )
        self.neo4j = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        self.reference_store = {
            "patients": {},
            "providers": {},
            "devices": {},
            "medications": {},
            "payers": {},
        }

    def close(self):
        self.neo4j.close()

    def process_reference_event(self, topic: str, raw_value: str):
        event = json.loads(raw_value)
        payload = json.loads(event.get("payload_json", "{}"))

        if topic == "healthcare.master.patients":
            patient_id = payload.get("patient_id") or event.get("patient_id")
            if patient_id:
                self.reference_store["patients"][patient_id] = payload
        elif topic == "healthcare.master.providers":
            provider_id = payload.get("provider_id") or event.get("provider_id")
            if provider_id:
                self.reference_store["providers"][provider_id] = payload
        elif topic == "healthcare.master.devices":
            device_id = payload.get("device_id")
            if device_id:
                self.reference_store["devices"][device_id] = payload
        elif topic == "healthcare.master.medications":
            medication = payload.get("medication")
            if medication:
                self.reference_store["medications"][medication] = payload
        elif topic == "healthcare.master.payers":
            payer = payload.get("payer")
            if payer:
                self.reference_store["payers"][payer] = payload

        print(f"Updated reference data from topic={topic}")

    def enrich_event(self, event: dict, payload: dict):
        patient_id = event.get("patient_id")
        provider_id = event.get("provider_id")
        device_id = payload.get("device_id")
        medication = payload.get("medication")
        payer = payload.get("payer")

        reference_data = {
            "patient": self.reference_store["patients"].get(patient_id),
            "provider": self.reference_store["providers"].get(provider_id),
            "device": self.reference_store["devices"].get(device_id),
            "medication": self.reference_store["medications"].get(medication),
            "payer": self.reference_store["payers"].get(payer),
        }

        payload["reference_data"] = reference_data
        event["enriched"] = True
        event["reference_hit_count"] = sum(1 for value in reference_data.values() if value is not None)
        return event, payload

    def process_event(self, raw_value: str):
        event = json.loads(raw_value)
        payload = json.loads(event.get("payload_json", "{}"))
        event, payload = self.enrich_event(event, payload)
        event["payload_json"] = json.dumps(payload)
        text = clinical_text(event)
        vector = stable_embedding(text)
        self.write_qdrant(event, payload, text, vector)
        self.write_neo4j(event, payload, text)
        print(
            f"Processed event_id={event['event_id']} type={event['event_type']} "
            f"patient={event.get('patient_id')} enrich_hits={event.get('reference_hit_count', 0)}"
        )

    def write_qdrant(self, event, payload, text, vector):
        point_id = int(hashlib.md5(event["event_id"].encode("utf-8")).hexdigest()[:16], 16)
        self.qdrant.upsert(
            collection_name=QDRANT_COLLECTION,
            points=[PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "event_id": event["event_id"],
                    "event_ts": event["event_ts"],
                    "event_type": event["event_type"],
                    "patient_id": event.get("patient_id"),
                    "source_system": event.get("source_system"),
                    "source_type": event.get("source_type"),
                    "enriched": event.get("enriched", False),
                    "reference_hit_count": event.get("reference_hit_count", 0),
                    "text": text,
                    "payload": payload,
                },
            )],
        )

    def write_neo4j(self, event, payload, text):
        with self.neo4j.session() as session:
            session.execute_write(self.merge_base_event, event, text)
            session.execute_write(self.merge_reference_context, event, payload)
            event_type = event["event_type"]
            if event_type == "CLINICAL_NOTE":
                session.execute_write(self.merge_clinical_note, event, payload)
            elif event_type == "LAB_RESULT":
                session.execute_write(self.merge_lab_result, event, payload)
            elif event_type == "VITAL_SIGN":
                session.execute_write(self.merge_device_reading, event, payload)
            elif event_type == "MEDICATION_ORDER":
                session.execute_write(self.merge_medication_order, event, payload)
            elif event_type == "CLAIM_STATUS":
                session.execute_write(self.merge_claim, event, payload)

    @staticmethod
    def merge_base_event(tx, event, text):
        tx.run(
            """
            MERGE (p:Patient {id: $patient_id})
            MERGE (src:SourceSystem {name: $source_system})
              SET src.type = $source_type
            MERGE (ce:ClinicalEvent {id: $event_id})
              SET ce.event_type = $event_type,
                  ce.event_ts = datetime($event_ts),
                  ce.text = $text,
                  ce.schema_version = $schema_version
            MERGE (ce)-[:ABOUT_PATIENT]->(p)
            MERGE (ce)-[:FROM_SOURCE]->(src)
            WITH ce
            CALL {
              WITH ce
              WITH ce WHERE $encounter_id IS NOT NULL
              MERGE (e:Encounter {id: $encounter_id})
              MERGE (ce)-[:DURING_ENCOUNTER]->(e)
              RETURN count(*) AS _
            }
            RETURN ce
            """,
            {
                "patient_id": event.get("patient_id"),
                "source_system": event.get("source_system"),
                "source_type": event.get("source_type"),
                "event_id": event.get("event_id"),
                "event_type": event.get("event_type"),
                "event_ts": event.get("event_ts"),
                "text": text,
                "schema_version": event.get("schema_version"),
                "encounter_id": event.get("encounter_id"),
            },
        )

    @staticmethod
    def merge_reference_context(tx, event, payload):
        reference = payload.get("reference_data", {})
        tx.run(
            """
            MATCH (p:Patient {id: $patient_id})
            WITH p
            CALL {
              WITH p
              WITH p WHERE $patient_ref IS NOT NULL
              SET p.name = coalesce($patient_ref.name, p.name),
                  p.sex = coalesce($patient_ref.sex, p.sex),
                  p.age = coalesce($patient_ref.age, p.age),
                  p.risk_tier = coalesce($patient_ref.risk_tier, p.risk_tier)
              RETURN count(*) AS _
            }
            WITH p
            CALL {
              WITH p
              WITH p WHERE $provider_id IS NOT NULL AND $provider_ref IS NOT NULL
              MERGE (pr:Provider {id: $provider_id})
              SET pr.name = coalesce($provider_ref.name, pr.name),
                  pr.specialty = coalesce($provider_ref.specialty, pr.specialty),
                  pr.organization = coalesce($provider_ref.organization, pr.organization)
              MERGE (p)-[:MANAGED_BY]->(pr)
              RETURN count(*) AS _
            }
            WITH p
            CALL {
              WITH p
              WITH p WHERE $device_id IS NOT NULL AND $device_ref IS NOT NULL
              MERGE (d:Device {id: $device_id})
              SET d.model = coalesce($device_ref.model, d.model),
                  d.vendor = coalesce($device_ref.vendor, d.vendor),
                  d.device_type = coalesce($device_ref.device_type, d.device_type)
              MERGE (p)-[:REGISTERED_DEVICE]->(d)
              RETURN count(*) AS _
            }
            WITH p
            CALL {
              WITH p
              WITH p WHERE $medication IS NOT NULL AND $medication_ref IS NOT NULL
              MERGE (m:Medication {name: $medication})
              SET m.drug_class = coalesce($medication_ref.drug_class, m.drug_class),
                  m.safety_tier = coalesce($medication_ref.safety_tier, m.safety_tier)
              MERGE (p)-[:KNOWN_MEDICATION]->(m)
              RETURN count(*) AS _
            }
            WITH p
            CALL {
              WITH p
              WITH p WHERE $payer IS NOT NULL AND $payer_ref IS NOT NULL
              MERGE (pay:Payer {name: $payer})
              SET pay.plan_type = coalesce($payer_ref.plan_type, pay.plan_type),
                  pay.region = coalesce($payer_ref.region, pay.region)
              MERGE (p)-[:COVERED_BY]->(pay)
              RETURN count(*) AS _
            }
            RETURN p
            """,
            {
                "patient_id": event.get("patient_id"),
                "provider_id": event.get("provider_id"),
                "device_id": payload.get("device_id"),
                "medication": payload.get("medication"),
                "payer": payload.get("payer"),
                "patient_ref": reference.get("patient"),
                "provider_ref": reference.get("provider"),
                "device_ref": reference.get("device"),
                "medication_ref": reference.get("medication"),
                "payer_ref": reference.get("payer"),
            },
        )

    @staticmethod
    def merge_clinical_note(tx, event, payload):
        tx.run(
            """
            MATCH (p:Patient {id: $patient_id})
            MATCH (ce:ClinicalEvent {id: $event_id})
            MERGE (c:Condition {name: $diagnosis})
            MERGE (s:Symptom {name: $symptom})
            MERGE (p)-[:HAS_CONDITION]->(c)
            MERGE (p)-[:HAS_SYMPTOM]->(s)
            MERGE (ce)-[:DOCUMENTS]->(c)
            MERGE (ce)-[:DOCUMENTS]->(s)
            """,
            {
                "patient_id": event["patient_id"],
                "event_id": event["event_id"],
                "diagnosis": payload.get("diagnosis"),
                "symptom": payload.get("symptom"),
            },
        )

    @staticmethod
    def merge_lab_result(tx, event, payload):
        tx.run(
            """
            MATCH (p:Patient {id: $patient_id})
            MATCH (ce:ClinicalEvent {id: $event_id})
            MERGE (o:Observation {id: $obs_id})
              SET o.name = $lab_name,
                  o.value = $value,
                  o.unit = $unit,
                  o.abnormal = $abnormal,
                  o.event_ts = datetime($event_ts)
            MERGE (p)-[:HAS_OBSERVATION]->(o)
            MERGE (ce)-[:DOCUMENTS]->(o)
            WITH o
            CALL {
              WITH o
              WITH o WHERE $lab_name = "Potassium" AND $value >= 5.5
              MERGE (c:Condition {name: "Hyperkalemia"})
              MERGE (o)-[:MAY_INDICATE {reason: "elevated_potassium"}]->(c)
              RETURN count(*) AS _
            }
            RETURN o
            """,
            {
                "patient_id": event["patient_id"],
                "event_id": event["event_id"],
                "obs_id": event["event_id"],
                "lab_name": payload.get("lab_name"),
                "value": payload.get("value"),
                "unit": payload.get("unit"),
                "abnormal": bool(payload.get("abnormal", False)),
                "event_ts": event["event_ts"],
            },
        )

    @staticmethod
    def merge_device_reading(tx, event, payload):
        tx.run(
            """
            MATCH (p:Patient {id: $patient_id})
            MATCH (ce:ClinicalEvent {id: $event_id})
            MERGE (d:Device {id: $device_id})
            MERGE (r:DeviceReading {id: $event_id})
              SET r.heart_rate = $heart_rate,
                  r.spo2 = $spo2,
                  r.systolic_bp = $systolic_bp,
                  r.diastolic_bp = $diastolic_bp,
                  r.event_ts = datetime($event_ts)
            MERGE (p)-[:HAS_DEVICE_READING]->(r)
            MERGE (r)-[:MEASURED_BY]->(d)
            MERGE (ce)-[:DOCUMENTS]->(r)
            """,
            {
                "patient_id": event["patient_id"],
                "event_id": event["event_id"],
                "device_id": payload.get("device_id"),
                "heart_rate": payload.get("heart_rate"),
                "spo2": payload.get("spo2"),
                "systolic_bp": payload.get("systolic_bp"),
                "diastolic_bp": payload.get("diastolic_bp"),
                "event_ts": event["event_ts"],
            },
        )

    @staticmethod
    def merge_medication_order(tx, event, payload):
        tx.run(
            """
            MATCH (p:Patient {id: $patient_id})
            MATCH (ce:ClinicalEvent {id: $event_id})
            MERGE (m:Medication {name: $medication})
            MERGE (mo:MedicationOrder {id: $event_id})
              SET mo.dose = $dose,
                  mo.route = $route,
                  mo.frequency = $frequency,
                  mo.event_ts = datetime($event_ts)
            MERGE (mo)-[:ORDERS_MEDICATION]->(m)
            MERGE (p)-[:HAS_MEDICATION_ORDER]->(mo)
            MERGE (ce)-[:DOCUMENTS]->(mo)
            """,
            {
                "patient_id": event["patient_id"],
                "event_id": event["event_id"],
                "medication": payload.get("medication"),
                "dose": payload.get("dose"),
                "route": payload.get("route"),
                "frequency": payload.get("frequency"),
                "event_ts": event["event_ts"],
            },
        )

    @staticmethod
    def merge_claim(tx, event, payload):
        tx.run(
            """
            MATCH (p:Patient {id: $patient_id})
            MATCH (ce:ClinicalEvent {id: $event_id})
            MERGE (c:Claim {id: $claim_id})
              SET c.payer = $payer,
                  c.procedure_code = $procedure_code,
                  c.status = $status,
                  c.event_ts = datetime($event_ts)
            MERGE (p)-[:HAS_CLAIM]->(c)
            MERGE (ce)-[:DOCUMENTS]->(c)
            """,
            {
                "patient_id": event["patient_id"],
                "event_id": event["event_id"],
                "claim_id": payload.get("claim_id"),
                "payer": payload.get("payer"),
                "procedure_code": payload.get("procedure_code"),
                "status": payload.get("status"),
                "event_ts": event["event_ts"],
            },
        )


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
        while True:
            msg = c.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise KafkaException(msg.error())
            try:
                topic = msg.topic()
                raw = msg.value().decode("utf-8")
                if topic in REFERENCE_TOPICS:
                    processor.process_reference_event(topic, raw)
                elif topic in TOPICS:
                    processor.process_event(raw)
                else:
                    print(f"Skipped message from unknown topic={topic}")
                c.commit(msg, asynchronous=False)
            except Exception as ex:
                print(f"FAILED processing key={msg.key()} error={ex}")
                time.sleep(1)
    finally:
        processor.close()
        c.close()


if __name__ == "__main__":
    main()
