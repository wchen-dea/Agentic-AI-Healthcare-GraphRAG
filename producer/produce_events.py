import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

import requests
from confluent_kafka import Producer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import MessageField, SerializationContext
from faker import Faker

fake = Faker()

BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092,localhost:9093,localhost:9094")
SCHEMA_REGISTRY_URL = os.getenv("SCHEMA_REGISTRY_URL", "http://localhost:8081")
INTERVAL = float(os.getenv("EVENT_INTERVAL_SECONDS", "1"))
SCHEMA_REGISTRY_STARTUP_TIMEOUT_SECONDS = int(
    os.getenv("SCHEMA_REGISTRY_STARTUP_TIMEOUT_SECONDS", "120")
)
SCHEMA_REGISTRY_RETRY_INTERVAL_SECONDS = float(
    os.getenv("SCHEMA_REGISTRY_RETRY_INTERVAL_SECONDS", "3")
)

producer = Producer({"bootstrap.servers": BOOTSTRAP})

TOPICS = {
    "EHR": "healthcare.ehr.events",
    "LIS": "healthcare.lab.results",
    "DEVICE": "healthcare.device.telemetry",
    "PHARMACY": "healthcare.pharmacy.orders",
    "CLAIMS": "healthcare.claims.events"
}

REFERENCE_TOPICS = {
    "PATIENTS": "healthcare.master.patients",
    "PROVIDERS": "healthcare.master.providers",
    "DEVICES": "healthcare.master.devices",
    "MEDICATIONS": "healthcare.master.medications",
    "PAYERS": "healthcare.master.payers",
}

PATIENTS = [f"patient-{i:04d}" for i in range(1, 101)]
PROVIDERS = [f"provider-{i:03d}" for i in range(1, 21)]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def wait_for_schema_registry():
    deadline = time.time() + SCHEMA_REGISTRY_STARTUP_TIMEOUT_SECONDS
    health_url = f"{SCHEMA_REGISTRY_URL}/subjects"

    while time.time() < deadline:
        try:
            response = requests.get(health_url, timeout=5)
            if response.status_code == 200:
                print("Schema Registry is ready.")
                return
            print(
                "Schema Registry not ready yet "
                f"status={response.status_code} body={response.text[:200]}"
            )
        except Exception as ex:
            print(f"Waiting for Schema Registry at {SCHEMA_REGISTRY_URL}: {ex}")
        time.sleep(SCHEMA_REGISTRY_RETRY_INTERVAL_SECONDS)

    raise RuntimeError(
        "Schema Registry did not become ready within "
        f"{SCHEMA_REGISTRY_STARTUP_TIMEOUT_SECONDS} seconds"
    )


def register_schema():
    with open("schemas/medical_event.avsc", "r", encoding="utf-8") as f:
        schema = f.read()
    for topic in list(TOPICS.values()) + list(REFERENCE_TOPICS.values()):
        subject = f"{topic}-value"
        url = f"{SCHEMA_REGISTRY_URL}/subjects/{subject}/versions"
        payload = {"schemaType": "AVRO", "schema": schema}
        deadline = time.time() + SCHEMA_REGISTRY_STARTUP_TIMEOUT_SECONDS
        last_error = None
        while time.time() < deadline:
            try:
                response = requests.post(url, json=payload, timeout=10)
                print(
                    "Schema registration "
                    f"subject={subject} status={response.status_code} "
                    f"response={response.text[:200]}"
                )
                if response.status_code in {200, 201, 409}:
                    break
                last_error = RuntimeError(
                    f"Unexpected schema registry status {response.status_code}: {response.text[:200]}"
                )
            except Exception as ex:
                last_error = ex
                print(f"Schema registration retry subject={subject}: {ex}")
            time.sleep(SCHEMA_REGISTRY_RETRY_INTERVAL_SECONDS)
        else:
            raise RuntimeError(
                f"Schema registration failed for subject={subject}: {last_error}"
            )


def build_avro_serializer():
    with open("schemas/medical_event.avsc", "r", encoding="utf-8") as f:
        schema = f.read()

    sr_client = SchemaRegistryClient({"url": SCHEMA_REGISTRY_URL})

    # Identity conversion because event_envelope already returns a dict matching the schema fields.
    return AvroSerializer(
        schema_registry_client=sr_client,
        schema_str=schema,
        to_dict=lambda obj, ctx: obj,
    )


def event_envelope(source_system, source_type, event_type, patient_id, encounter_id, provider_id, payload):
    return {
        "event_id": str(uuid.uuid4()),
        "event_ts": now_iso(),
        "source_system": source_system,
        "source_type": source_type,
        "event_type": event_type,
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "provider_id": provider_id,
        "payload_json": json.dumps(payload),
        "schema_version": "1.0.0"
    }


def ehr_event():
    patient = random.choice(PATIENTS)
    encounter = f"enc-{random.randint(1000, 9999)}"
    diagnosis = random.choice(["Hypertension", "Diabetes", "Pneumonia", "Asthma", "Hyperkalemia"])
    symptom = random.choice(["fever", "cough", "fatigue", "chest pain", "shortness of breath"])
    system = random.choice(["Epic", "Cerner"])
    payload = {
        "diagnosis": diagnosis,
        "symptom": symptom,
        "note": f"Patient presents with {symptom}. Assessment suggests {diagnosis}.",
        "system": system
    }
    return TOPICS["EHR"], event_envelope(system, "EHR", "CLINICAL_NOTE", patient, encounter, random.choice(PROVIDERS), payload)


def lab_event():
    patient = random.choice(PATIENTS)
    lab = random.choice([
        ("Potassium", round(random.uniform(3.0, 7.2), 1), "mmol/L"),
        ("Glucose", random.randint(70, 280), "mg/dL"),
        ("Creatinine", round(random.uniform(0.6, 3.0), 1), "mg/dL")
    ])
    payload = {
        "lab_name": lab[0],
        "value": lab[1],
        "unit": lab[2],
        "abnormal": lab[0] == "Potassium" and lab[1] >= 5.5
    }
    return TOPICS["LIS"], event_envelope("LIS", "LAB", "LAB_RESULT", patient, f"enc-{random.randint(1000,9999)}", None, payload)


def device_event():
    patient = random.choice(PATIENTS)
    payload = {
        "device_id": f"device-{random.randint(1, 20)}",
        "heart_rate": random.randint(55, 145),
        "spo2": random.randint(88, 100),
        "systolic_bp": random.randint(90, 180),
        "diastolic_bp": random.randint(55, 110)
    }
    return TOPICS["DEVICE"], event_envelope("IoT-Monitor", "DEVICE", "VITAL_SIGN", patient, f"enc-{random.randint(1000,9999)}", None, payload)


def pharmacy_event():
    patient = random.choice(PATIENTS)
    med = random.choice(["Warfarin", "Lisinopril", "Metformin", "Azithromycin", "Albuterol"])
    payload = {
        "medication": med,
        "dose": random.choice(["5mg", "10mg", "500mg", "250mg"]),
        "route": "oral",
        "frequency": random.choice(["daily", "twice daily", "as needed"])
    }
    return TOPICS["PHARMACY"], event_envelope("Pharmacy", "PHARMACY", "MEDICATION_ORDER", patient, f"enc-{random.randint(1000,9999)}", random.choice(PROVIDERS), payload)


def claims_event():
    patient = random.choice(PATIENTS)
    payload = {
        "claim_id": f"claim-{uuid.uuid4()}",
        "payer": random.choice(["Aetna", "United", "BCBS", "Medicare"]),
        "procedure_code": random.choice(["99213", "80053", "93000", "71046"]),
        "status": random.choice(["submitted", "approved", "denied"])
    }
    return TOPICS["CLAIMS"], event_envelope("ClaimsSystem", "CLAIMS", "CLAIM_STATUS", patient, None, None, payload)


def patient_reference_event():
    patient = random.choice(PATIENTS)
    payload = {
        "patient_id": patient,
        "name": fake.name(),
        "sex": random.choice(["F", "M"]),
        "age": random.randint(18, 90),
        "risk_tier": random.choice(["low", "medium", "high"]),
    }
    return (
        REFERENCE_TOPICS["PATIENTS"],
        event_envelope("MasterData", "REFERENCE", "PATIENT_MASTER_UPSERT", patient, None, None, payload),
    )


def provider_reference_event():
    provider = random.choice(PROVIDERS)
    payload = {
        "provider_id": provider,
        "name": fake.name(),
        "specialty": random.choice(["Cardiology", "Pulmonology", "Endocrinology", "Primary Care"]),
        "organization": random.choice(["City Hospital", "County Clinic", "Regional Health"]),
    }
    return (
        REFERENCE_TOPICS["PROVIDERS"],
        event_envelope("MasterData", "REFERENCE", "PROVIDER_MASTER_UPSERT", None, None, provider, payload),
    )


def device_reference_event():
    device_id = f"device-{random.randint(1, 20)}"
    payload = {
        "device_id": device_id,
        "model": random.choice(["CardioMon-100", "PulseTrack-X", "VitalSense-Pro"]),
        "vendor": random.choice(["MedTech", "HealthIoT", "VitalWorks"]),
        "device_type": random.choice(["monitor", "wearable", "bedside"]),
    }
    return (
        REFERENCE_TOPICS["DEVICES"],
        event_envelope("MasterData", "REFERENCE", "DEVICE_MASTER_UPSERT", None, None, None, payload),
    )


def medication_reference_event():
    medication = random.choice(["Warfarin", "Lisinopril", "Metformin", "Azithromycin", "Albuterol"])
    payload = {
        "medication": medication,
        "drug_class": random.choice(["Anticoagulant", "Antihypertensive", "Antidiabetic", "Antibiotic", "Bronchodilator"]),
        "safety_tier": random.choice(["routine", "monitor", "high-alert"]),
    }
    return (
        REFERENCE_TOPICS["MEDICATIONS"],
        event_envelope("MasterData", "REFERENCE", "MEDICATION_MASTER_UPSERT", None, None, None, payload),
    )


def payer_reference_event():
    payer = random.choice(["Aetna", "United", "BCBS", "Medicare"])
    payload = {
        "payer": payer,
        "plan_type": random.choice(["HMO", "PPO", "Government"]),
        "region": random.choice(["Northeast", "South", "Midwest", "West"]),
    }
    return (
        REFERENCE_TOPICS["PAYERS"],
        event_envelope("MasterData", "REFERENCE", "PAYER_MASTER_UPSERT", None, None, None, payload),
    )


GENERATORS = [ehr_event, lab_event, device_event, pharmacy_event, claims_event]
REFERENCE_GENERATORS = [
    patient_reference_event,
    provider_reference_event,
    device_reference_event,
    medication_reference_event,
    payer_reference_event,
]
wait_for_schema_registry()
register_schema()
avro_serializer = build_avro_serializer()

while True:
    if random.random() < 0.2:
        topic, event = random.choice(REFERENCE_GENERATORS)()
    else:
        topic, event = random.choice(GENERATORS)()
    key = event["patient_id"] or event["event_id"]
    avro_payload = avro_serializer(event, SerializationContext(topic, MessageField.VALUE))
    producer.produce(topic, key=key.encode("utf-8"), value=avro_payload)
    producer.flush()
    print(f"Produced {event['event_type']} to {topic}: {event['event_id']}")
    time.sleep(INTERVAL)
