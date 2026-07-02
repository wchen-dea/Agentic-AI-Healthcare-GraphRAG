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


DIAGNOSES = [
    "Hypertension", "Diabetes", "Pneumonia", "Asthma", "Hyperkalemia",
    "Atrial Fibrillation", "COPD", "Chronic Kidney Disease", "Heart Failure",
    "Sepsis", "Urinary Tract Infection", "Hypothyroidism", "Anemia",
    "GERD", "Osteoporosis", "Type 2 Diabetes Mellitus", "Hyperlipidemia",
    "Acute Myocardial Infarction", "Stroke", "Deep Vein Thrombosis",
    "Pulmonary Embolism", "Cellulitis", "Appendicitis", "Pancreatitis",
]

SYMPTOMS = [
    "fever", "cough", "fatigue", "chest pain", "shortness of breath",
    "nausea", "dizziness", "headache", "joint pain", "swelling",
    "back pain", "palpitations", "confusion", "abdominal pain",
    "vomiting", "weight loss", "night sweats", "blurred vision",
    "urinary frequency", "leg cramps",
]

EHR_SYSTEMS = ["Epic", "Cerner", "Meditech", "Allscripts", "eClinicalWorks", "Athenahealth"]

NOTE_TEMPLATES = [
    "Patient presents with {symptom}. Assessment suggests {diagnosis}.",
    "Chief complaint: {symptom}. Working diagnosis: {diagnosis}.",
    "Patient reports {symptom} for 3 days. Impression: {diagnosis}.",
    "Evaluation reveals {symptom}. Clinical picture consistent with {diagnosis}.",
    "Follow-up visit. Ongoing {symptom}. Diagnosis confirmed: {diagnosis}.",
    "{symptom} noted on examination. Differential includes {diagnosis}.",
]


def ehr_event():
    patient = random.choice(PATIENTS)
    encounter = f"enc-{random.randint(1000, 9999)}"
    diagnosis = random.choice(DIAGNOSES)
    symptom = random.choice(SYMPTOMS)
    system = random.choice(EHR_SYSTEMS)
    note = random.choice(NOTE_TEMPLATES).format(symptom=symptom, diagnosis=diagnosis)
    payload = {
        "diagnosis": diagnosis,
        "symptom": symptom,
        "note": note,
        "system": system,
        "icd10_code": fake.bothify(text="?##.#", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    }
    return TOPICS["EHR"], event_envelope(system, "EHR", "CLINICAL_NOTE", patient, encounter, random.choice(PROVIDERS), payload)


LAB_TESTS = [
    ("Potassium",     lambda: round(random.uniform(3.0, 7.2), 1),   "mmol/L",  lambda n, v: n == "Potassium" and v >= 5.5),
    ("Sodium",        lambda: random.randint(128, 148),               "mmol/L",  lambda n, v: v < 135 or v > 145),
    ("Glucose",       lambda: random.randint(60, 380),                "mg/dL",   lambda n, v: v < 70 or v > 180),
    ("Creatinine",    lambda: round(random.uniform(0.5, 4.5), 1),    "mg/dL",   lambda n, v: v > 1.2),
    ("BUN",           lambda: random.randint(7, 60),                  "mg/dL",   lambda n, v: v > 25),
    ("HbA1c",         lambda: round(random.uniform(4.5, 11.5), 1),   "%",        lambda n, v: v >= 6.5),
    ("WBC",           lambda: round(random.uniform(2.5, 18.0), 1),   "10^3/uL", lambda n, v: v < 4.0 or v > 11.0),
    ("Hemoglobin",    lambda: round(random.uniform(6.5, 17.5), 1),   "g/dL",    lambda n, v: v < 12.0),
    ("Platelets",     lambda: random.randint(50, 450),                "10^3/uL", lambda n, v: v < 150 or v > 400),
    ("TSH",           lambda: round(random.uniform(0.1, 8.0), 2),    "mIU/L",   lambda n, v: v < 0.5 or v > 4.5),
    ("eGFR",          lambda: random.randint(15, 105),                "mL/min",  lambda n, v: v < 60),
    ("LDL",           lambda: random.randint(60, 220),                "mg/dL",   lambda n, v: v > 130),
    ("HDL",           lambda: random.randint(25, 90),                 "mg/dL",   lambda n, v: v < 40),
    ("ALT",           lambda: random.randint(7, 180),                 "U/L",     lambda n, v: v > 56),
    ("AST",           lambda: random.randint(10, 200),                "U/L",     lambda n, v: v > 40),
    ("Troponin I",    lambda: round(random.uniform(0.0, 2.5), 3),    "ng/mL",   lambda n, v: v > 0.04),
    ("INR",           lambda: round(random.uniform(0.8, 4.5), 1),    "ratio",   lambda n, v: v > 3.0),
    ("Procalcitonin", lambda: round(random.uniform(0.0, 5.0), 2),    "ng/mL",   lambda n, v: v > 0.5),
]


def lab_event():
    patient = random.choice(PATIENTS)
    name, value_fn, unit, abnormal_fn = random.choice(LAB_TESTS)
    value = value_fn()
    payload = {
        "lab_name": name,
        "value": value,
        "unit": unit,
        "abnormal": abnormal_fn(name, value),
        "lab_panel": random.choice(["BMP", "CMP", "CBC", "Lipid Panel", "LFT", "Thyroid", "Coagulation", "Cardiac", "Standalone"]),
        "specimen_type": random.choice(["serum", "plasma", "whole blood", "urine"]),
    }
    return TOPICS["LIS"], event_envelope("LIS", "LAB", "LAB_RESULT", patient, f"enc-{random.randint(1000,9999)}", None, payload)


DEVICE_SOURCES = ["IoT-Monitor", "BedSideMon", "WearableSensor", "TelemetryHub", "RemotePatientMon"]


def device_event():
    patient = random.choice(PATIENTS)
    source = random.choice(DEVICE_SOURCES)
    payload = {
        "device_id": f"device-{random.randint(1, 40)}",
        "device_type": random.choice(["monitor", "wearable", "bedside", "implant", "patch"]),
        "heart_rate": random.randint(40, 160),
        "spo2": random.randint(84, 100),
        "systolic_bp": random.randint(80, 200),
        "diastolic_bp": random.randint(45, 120),
        "temperature_c": round(random.uniform(35.5, 40.2), 1),
        "respiratory_rate": random.randint(10, 30),
        "glucose_mg_dl": random.choice([None, random.randint(60, 380)]),
        "alert": random.choice([None, None, None, "tachycardia", "hypoxia", "hypertension", "bradycardia"]),
    }
    return TOPICS["DEVICE"], event_envelope(source, "DEVICE", "VITAL_SIGN", patient, f"enc-{random.randint(1000,9999)}", None, payload)


MEDICATIONS = [
    ("Warfarin",              "Anticoagulant",      ["1mg", "2mg", "5mg"],             "oral"),
    ("Lisinopril",            "Antihypertensive",   ["5mg", "10mg", "20mg", "40mg"],   "oral"),
    ("Metformin",             "Antidiabetic",        ["500mg", "850mg", "1000mg"],      "oral"),
    ("Azithromycin",          "Antibiotic",          ["250mg", "500mg"],                "oral"),
    ("Albuterol",             "Bronchodilator",      ["2.5mg"],                         "inhaled"),
    ("Amlodipine",            "Antihypertensive",   ["5mg", "10mg"],                   "oral"),
    ("Atorvastatin",          "Statin",              ["10mg", "20mg", "40mg", "80mg"], "oral"),
    ("Omeprazole",            "PPI",                 ["20mg", "40mg"],                  "oral"),
    ("Losartan",              "Antihypertensive",   ["25mg", "50mg", "100mg"],         "oral"),
    ("Metoprolol",            "Beta-Blocker",        ["25mg", "50mg", "100mg"],         "oral"),
    ("Levothyroxine",         "Thyroid Hormone",     ["25mcg", "50mcg", "100mcg"],     "oral"),
    ("Gabapentin",            "Anticonvulsant",      ["100mg", "300mg", "600mg"],       "oral"),
    ("Sertraline",            "Antidepressant",      ["25mg", "50mg", "100mg"],         "oral"),
    ("Hydrochlorothiazide",   "Diuretic",            ["12.5mg", "25mg"],               "oral"),
    ("Prednisone",            "Corticosteroid",      ["5mg", "10mg", "20mg", "40mg"], "oral"),
    ("Amoxicillin",           "Antibiotic",          ["250mg", "500mg"],                "oral"),
    ("Heparin",               "Anticoagulant",      ["5000 units"],                    "subcutaneous"),
    ("Insulin Glargine",      "Antidiabetic",        ["10 units", "20 units", "40 units"], "subcutaneous"),
    ("Vancomycin",            "Antibiotic",          ["500mg", "1000mg", "1500mg"],     "IV"),
    ("Morphine",              "Opioid Analgesic",    ["2mg", "4mg", "8mg"],            "IV"),
    ("Furosemide",            "Diuretic",            ["20mg", "40mg", "80mg"],          "oral"),
    ("Clopidogrel",           "Antiplatelet",        ["75mg"],                          "oral"),
    ("Spironolactone",        "Diuretic",            ["12.5mg", "25mg", "50mg"],        "oral"),
    ("Dexamethasone",         "Corticosteroid",      ["4mg", "8mg"],                    "IV"),
]

ORDER_TYPES = ["new", "renewal", "discontinue", "dose_change"]


def pharmacy_event():
    patient = random.choice(PATIENTS)
    med_name, drug_class, doses, default_route = random.choice(MEDICATIONS)
    route = default_route if random.random() > 0.1 else random.choice(["oral", "IV", "subcutaneous", "inhaled", "topical", "sublingual"])
    payload = {
        "medication": med_name,
        "drug_class": drug_class,
        "dose": random.choice(doses),
        "route": route,
        "frequency": random.choice(["daily", "twice daily", "three times daily", "every 8 hours", "every 12 hours", "at bedtime", "weekly", "as needed", "every 6 hours"]),
        "order_type": random.choice(ORDER_TYPES),
        "days_supply": random.choice([7, 14, 30, 60, 90]),
    }
    return TOPICS["PHARMACY"], event_envelope("Pharmacy", "PHARMACY", "MEDICATION_ORDER", patient, f"enc-{random.randint(1000,9999)}", random.choice(PROVIDERS), payload)


PAYERS = ["Aetna", "United", "BCBS", "Medicare", "Medicaid", "Cigna", "Humana", "Kaiser", "Tricare", "Centene"]

PROCEDURE_CODES = [
    # E&M
    ("99213", "Office visit, established patient, moderate"),
    ("99214", "Office visit, established patient, high complexity"),
    ("99232", "Subsequent hospital care"),
    ("99285", "Emergency dept visit, high complexity"),
    # Lab
    ("80053", "Comprehensive metabolic panel"),
    ("80061", "Lipid panel"),
    ("85025", "CBC with differential"),
    ("83036", "HbA1c"),
    # Cardiac
    ("93000", "ECG with interpretation"),
    ("93306", "Echocardiography"),
    ("93458", "Cardiac catheterization"),
    # Imaging
    ("71046", "Chest X-ray, 2 views"),
    ("74177", "CT abdomen and pelvis with contrast"),
    ("70553", "MRI brain with contrast"),
    # Procedures
    ("36415", "Venipuncture"),
    ("43239", "Upper GI endoscopy with biopsy"),
    ("45378", "Colonoscopy, diagnostic"),
    ("27447", "Total knee arthroplasty"),
]

DIAGNOSIS_CODES = ["I10", "E11.9", "J18.9", "J44.1", "N18.3", "I48.91", "E03.9", "D64.9", "K21.0", "I50.9"]


def claims_event():
    patient = random.choice(PATIENTS)
    proc_code, proc_desc = random.choice(PROCEDURE_CODES)
    amount = round(random.uniform(50, 12000), 2)
    payload = {
        "claim_id": f"claim-{uuid.uuid4()}",
        "payer": random.choice(PAYERS),
        "procedure_code": proc_code,
        "procedure_description": proc_desc,
        "diagnosis_code": random.choice(DIAGNOSIS_CODES),
        "billed_amount": amount,
        "allowed_amount": round(amount * random.uniform(0.4, 1.0), 2),
        "status": random.choice(["submitted", "approved", "denied", "pending", "appealed", "partially_approved"]),
        "claim_type": random.choice(["professional", "institutional", "dental", "pharmacy"]),
        "service_date": fake.date_between(start_date="-90d", end_date="today").isoformat(),
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
        "specialty": random.choice([
            "Cardiology", "Pulmonology", "Endocrinology", "Primary Care",
            "Nephrology", "Neurology", "Oncology", "Orthopedics",
            "Psychiatry", "Radiology", "Emergency Medicine", "Gastroenterology",
            "Infectious Disease", "Rheumatology", "Hematology", "Hospitalist",
        ]),
        "organization": random.choice([
            "City Hospital", "County Clinic", "Regional Health",
            "University Medical Center", "Community Health Network",
            "Metro General Hospital", "Riverside Medical Group", "Apex Health System",
        ]),
        "npi": fake.numerify(text="##########"),
    }
    return (
        REFERENCE_TOPICS["PROVIDERS"],
        event_envelope("MasterData", "REFERENCE", "PROVIDER_MASTER_UPSERT", None, None, provider, payload),
    )


def device_reference_event():
    device_id = f"device-{random.randint(1, 40)}"
    payload = {
        "device_id": device_id,
        "model": random.choice([
            "CardioMon-100", "PulseTrack-X", "VitalSense-Pro",
            "OmniWatch-500", "NovaBeat-3", "NeuroSync-II",
            "GlucoSense-7", "RespiGuard-4", "PatchMonitor-Elite",
        ]),
        "vendor": random.choice(["MedTech", "HealthIoT", "VitalWorks", "BioSense", "ClinDevice", "NovaMed"]),
        "device_type": random.choice(["monitor", "wearable", "bedside", "implant", "patch", "infusion_pump"]),
        "firmware_version": fake.numerify(text="#.#.##"),
        "connectivity": random.choice(["BLE", "WiFi", "LTE", "Zigbee", "HL7-FHIR"]),
    }
    return (
        REFERENCE_TOPICS["DEVICES"],
        event_envelope("MasterData", "REFERENCE", "DEVICE_MASTER_UPSERT", None, None, None, payload),
    )


def medication_reference_event():
    med_name, drug_class, _, _ = random.choice(MEDICATIONS)
    payload = {
        "medication": med_name,
        "drug_class": drug_class,
        "safety_tier": random.choice(["routine", "monitor", "high-alert"]),
        "requires_monitoring": random.choice([True, False]),
        "controlled_substance": med_name in {"Morphine", "Gabapentin"},
    }
    return (
        REFERENCE_TOPICS["MEDICATIONS"],
        event_envelope("MasterData", "REFERENCE", "MEDICATION_MASTER_UPSERT", None, None, None, payload),
    )


def payer_reference_event():
    payer = random.choice(PAYERS)
    payload = {
        "payer": payer,
        "plan_type": random.choice(["HMO", "PPO", "EPO", "POS", "HDHP", "Government", "Medicaid Managed Care"]),
        "region": random.choice(["Northeast", "South", "Midwest", "West", "Southwest", "Northwest", "National"]),
        "network_tier": random.choice(["in-network", "out-of-network", "preferred"]),
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
