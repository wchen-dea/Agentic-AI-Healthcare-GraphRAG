import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

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
TRANSACTION_EVENTS_PER_INTERVAL = max(
    0,
    int(os.getenv("TRANSACTION_EVENTS_PER_INTERVAL", "3")),
)
REFERENCE_EVENTS_PER_INTERVAL = max(
    0,
    int(os.getenv("REFERENCE_EVENTS_PER_INTERVAL", "3")),
)
PATIENT_POOL_SIZE = max(100, int(os.getenv("PATIENT_POOL_SIZE", "1000")))
PROVIDER_POOL_SIZE = max(20, int(os.getenv("PROVIDER_POOL_SIZE", "200")))
DEVICE_POOL_SIZE = max(40, int(os.getenv("DEVICE_POOL_SIZE", "400")))
HOT_PATIENT_POOL_SIZE = max(10, int(os.getenv("HOT_PATIENT_POOL_SIZE", "120")))
HOT_PROVIDER_POOL_SIZE = max(5, int(os.getenv("HOT_PROVIDER_POOL_SIZE", "40")))
HOT_ENTITY_PROBABILITY = min(max(float(os.getenv("HOT_ENTITY_PROBABILITY", "0.7")), 0.0), 1.0)
LATE_EVENT_PROBABILITY = min(max(float(os.getenv("LATE_EVENT_PROBABILITY", "0.12")), 0.0), 1.0)
CORRECTION_EVENT_PROBABILITY = min(max(float(os.getenv("CORRECTION_EVENT_PROBABILITY", "0.06")), 0.0), 1.0)
FOLLOWUP_CORRELATION_PROBABILITY = min(max(float(os.getenv("FOLLOWUP_CORRELATION_PROBABILITY", "0.45")), 0.0), 1.0)
BATCH_BURST_PROBABILITY = min(max(float(os.getenv("BATCH_BURST_PROBABILITY", "0.3")), 0.0), 1.0)
BATCH_BURST_MULTIPLIER = max(1, int(os.getenv("BATCH_BURST_MULTIPLIER", "3")))
SHIFT_HANDOFF_HOURS = {
    int(h.strip()) for h in os.getenv("SHIFT_HANDOFF_HOURS", "7,15,23").split(",") if h.strip().isdigit()
}
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

PATIENTS = [f"patient-{i:04d}" for i in range(1, PATIENT_POOL_SIZE + 1)]
PROVIDERS = [f"provider-{i:03d}" for i in range(1, PROVIDER_POOL_SIZE + 1)]
HOT_PATIENTS = PATIENTS[: min(HOT_PATIENT_POOL_SIZE, len(PATIENTS))]
HOT_PROVIDERS = PROVIDERS[: min(HOT_PROVIDER_POOL_SIZE, len(PROVIDERS))]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def choose_patient_id() -> str:
    if HOT_PATIENTS and random.random() < HOT_ENTITY_PROBABILITY:
        return random.choice(HOT_PATIENTS)
    return random.choice(PATIENTS)


def choose_provider_id() -> str:
    if HOT_PROVIDERS and random.random() < HOT_ENTITY_PROBABILITY:
        return random.choice(HOT_PROVIDERS)
    return random.choice(PROVIDERS)


def _iso_shifted(hours: int = 0, minutes: int = 0) -> str:
    shifted = datetime.now(timezone.utc) + timedelta(hours=hours, minutes=minutes)
    return shifted.isoformat()


def apply_temporal_noise(event: dict, payload: dict) -> tuple[dict, dict]:
    # Late-arriving events simulate ingest delay while preserving event ordering pressure.
    if random.random() < LATE_EVENT_PROBABILITY:
        lag_minutes = random.randint(5, 180)
        event["event_ts"] = _iso_shifted(minutes=-lag_minutes)
        payload["late_arrival_minutes"] = lag_minutes

    # Correction events model amended clinical and claims records.
    if random.random() < CORRECTION_EVENT_PROBABILITY:
        payload["is_correction"] = True
        payload["correction_of_event_id"] = f"evt-{uuid.uuid4()}"
    else:
        payload["is_correction"] = False

    event["payload_json"] = json.dumps(payload)
    return event, payload


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
    "Coronary Artery Disease", "Chronic Liver Disease", "Rheumatoid Arthritis", "Migraine",
    "Depression", "Anxiety Disorder", "Obstructive Sleep Apnea", "Hypokalemia",
    "Hyperthyroidism", "Hyponatremia", "Hypernatremia", "Acute Kidney Injury",
    "Gastroenteritis", "Diverticulitis", "Peripheral Artery Disease", "Psoriasis",
    "Gout", "Chronic Pain Syndrome", "Dementia", "Epilepsy",
    "Chronic Venous Insufficiency", "Multiple Sclerosis", "Parkinson Disease", "Irritable Bowel Syndrome",
]

SYMPTOMS = [
    "fever", "cough", "fatigue", "chest pain", "shortness of breath",
    "nausea", "dizziness", "headache", "joint pain", "swelling",
    "back pain", "palpitations", "confusion", "abdominal pain",
    "vomiting", "weight loss", "night sweats", "blurred vision",
    "urinary frequency", "leg cramps",
    "chills", "wheezing", "rash", "syncope", "numbness",
    "tingling", "diarrhea", "constipation", "dysuria", "hematuria",
    "sore throat", "muscle aches", "insomnia", "tremor", "itching",
    "loss of appetite", "polyuria", "polydipsia", "restlessness", "difficulty walking",
]

EHR_SYSTEMS = [
    "Epic", "Cerner", "Meditech", "Allscripts", "eClinicalWorks", "Athenahealth",
    "NextGen", "Practice Fusion", "Greenway Health", "GE Centricity", "DrChrono", "CareCloud",
]

NOTE_TEMPLATES = [
    "Patient presents with {symptom}. Assessment suggests {diagnosis}.",
    "Chief complaint: {symptom}. Working diagnosis: {diagnosis}.",
    "Patient reports {symptom} for 3 days. Impression: {diagnosis}.",
    "Evaluation reveals {symptom}. Clinical picture consistent with {diagnosis}.",
    "Follow-up visit. Ongoing {symptom}. Diagnosis confirmed: {diagnosis}.",
    "{symptom} noted on examination. Differential includes {diagnosis}.",
    "On triage, patient notes {symptom}. Preliminary diagnosis: {diagnosis}.",
    "Progress note: persistent {symptom}; plan of care aligned with {diagnosis}.",
    "Consult report documents {symptom}. Impression remains {diagnosis}.",
    "Discharge summary references {symptom} with final diagnosis of {diagnosis}.",
    "Telehealth follow-up for {symptom}; likely etiology is {diagnosis}.",
    "Problem-focused visit due to {symptom}. Assessment favors {diagnosis}.",
]


def ehr_event():
    patient = choose_patient_id()
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
    event = event_envelope(system, "EHR", "CLINICAL_NOTE", patient, encounter, choose_provider_id(), payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["EHR"], event


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
    ("Calcium",       lambda: round(random.uniform(7.0, 12.0), 1),    "mg/dL",   lambda n, v: v < 8.5 or v > 10.5),
    ("Magnesium",     lambda: round(random.uniform(1.0, 3.5), 1),     "mg/dL",   lambda n, v: v < 1.6 or v > 2.6),
    ("Phosphate",     lambda: round(random.uniform(1.5, 6.5), 1),     "mg/dL",   lambda n, v: v < 2.5 or v > 4.5),
    ("C-Reactive Protein", lambda: round(random.uniform(0.0, 30.0), 1), "mg/L", lambda n, v: v > 10.0),
    ("ESR",           lambda: random.randint(1, 80),                  "mm/hr",   lambda n, v: v > 20),
    ("Lactate",       lambda: round(random.uniform(0.3, 6.0), 1),     "mmol/L",  lambda n, v: v > 2.0),
    ("BNP",           lambda: random.randint(5, 2500),                "pg/mL",   lambda n, v: v > 100),
    ("Total Bilirubin", lambda: round(random.uniform(0.1, 4.0), 1),   "mg/dL",   lambda n, v: v > 1.2),
    ("Albumin",       lambda: round(random.uniform(2.0, 5.5), 1),     "g/dL",    lambda n, v: v < 3.5),
    ("Alkaline Phosphatase", lambda: random.randint(40, 300),         "U/L",     lambda n, v: v > 147),
    ("D-Dimer",       lambda: round(random.uniform(0.1, 5.0), 2),     "mg/L FEU", lambda n, v: v > 0.5),
    ("Ferritin",      lambda: random.randint(8, 900),                 "ng/mL",   lambda n, v: v < 30 or v > 400),
    ("Uric Acid",     lambda: round(random.uniform(2.0, 10.0), 1),    "mg/dL",   lambda n, v: v > 7.0),
    ("Creatine Kinase", lambda: random.randint(20, 1200),             "U/L",     lambda n, v: v > 200),
    ("Arterial pH",   lambda: round(random.uniform(7.1, 7.6), 2),     "pH",      lambda n, v: v < 7.35 or v > 7.45),
    ("PaCO2",         lambda: random.randint(20, 65),                 "mmHg",    lambda n, v: v < 35 or v > 45),
    ("PaO2",          lambda: random.randint(50, 120),                "mmHg",    lambda n, v: v < 80),
    ("Serum Osmolality", lambda: random.randint(250, 320),            "mOsm/kg", lambda n, v: v < 275 or v > 295),
]


def lab_event():
    patient = choose_patient_id()
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
    event = event_envelope("LIS", "LAB", "LAB_RESULT", patient, f"enc-{random.randint(1000,9999)}", None, payload)
    event, _ = apply_temporal_noise(event, payload)
    if payload["abnormal"] and name in {"Potassium", "Troponin I", "Glucose", "Lactate"}:
        if random.random() < FOLLOWUP_CORRELATION_PROBABILITY:
            follow_topic, follow_event = medication_administration_event(patient_id=patient, force_state="administered")
            follow_payload = json.loads(follow_event["payload_json"])
            follow_payload["correlated_with_lab_event_id"] = event["event_id"]
            follow_payload["correlated_with_lab_name"] = name
            follow_event["payload_json"] = json.dumps(follow_payload)
            PENDING_FOLLOWUPS.append((follow_topic, follow_event))
    return TOPICS["LIS"], event


DEVICE_SOURCES = [
    "IoT-Monitor", "BedSideMon", "WearableSensor", "TelemetryHub", "RemotePatientMon",
    "HomeVitalsBridge", "AmbulatoryTelemetry", "SmartPatchGateway", "StepDownMon", "ICUHub",
]


def device_event():
    patient = choose_patient_id()
    source = random.choice(DEVICE_SOURCES)
    payload = {
        "device_id": f"device-{random.randint(1, DEVICE_POOL_SIZE)}",
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
    event = event_envelope(source, "DEVICE", "VITAL_SIGN", patient, f"enc-{random.randint(1000,9999)}", None, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["DEVICE"], event


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
    ("Aspirin",               "Antiplatelet",        ["81mg", "325mg"],                 "oral"),
    ("Insulin Lispro",        "Antidiabetic",        ["5 units", "10 units", "15 units"], "subcutaneous"),
    ("Enoxaparin",            "Anticoagulant",       ["40mg", "60mg", "80mg"],          "subcutaneous"),
    ("Ceftriaxone",           "Antibiotic",          ["1g", "2g"],                       "IV"),
    ("Piperacillin-Tazobactam", "Antibiotic",        ["2.25g", "3.375g", "4.5g"],       "IV"),
    ("Levofloxacin",          "Antibiotic",          ["250mg", "500mg", "750mg"],       "oral"),
    ("Apixaban",              "Anticoagulant",       ["2.5mg", "5mg"],                   "oral"),
    ("Rivaroxaban",           "Anticoagulant",       ["10mg", "15mg", "20mg"],          "oral"),
    ("Diltiazem",             "Calcium Channel Blocker", ["120mg", "180mg", "240mg"],  "oral"),
    ("Carvedilol",            "Beta-Blocker",        ["3.125mg", "6.25mg", "12.5mg", "25mg"], "oral"),
    ("Nitroglycerin",         "Vasodilator",         ["0.4mg"],                           "sublingual"),
    ("Pantoprazole",          "PPI",                 ["20mg", "40mg"],                   "oral"),
    ("Famotidine",            "H2 Blocker",          ["20mg", "40mg"],                   "oral"),
    ("Ondansetron",           "Antiemetic",          ["4mg", "8mg"],                     "IV"),
    ("Acetaminophen",         "Analgesic",           ["325mg", "500mg", "650mg"],       "oral"),
    ("Ibuprofen",             "NSAID",               ["200mg", "400mg", "600mg", "800mg"], "oral"),
    ("Cefepime",              "Antibiotic",          ["1g", "2g"],                       "IV"),
    ("Meropenem",             "Antibiotic",          ["500mg", "1g"],                    "IV"),
    ("Linezolid",             "Antibiotic",          ["600mg"],                           "oral"),
    ("Digoxin",               "Cardiac Glycoside",   ["0.125mg", "0.25mg"],              "oral"),
    ("Sacubitril-Valsartan",  "Heart Failure Therapy", ["24/26mg", "49/51mg", "97/103mg"], "oral"),
    ("Empagliflozin",         "Antidiabetic",        ["10mg", "25mg"],                   "oral"),
    ("Tamsulosin",            "Alpha Blocker",       ["0.4mg", "0.8mg"],                 "oral"),
    ("Hydralazine",           "Vasodilator",         ["10mg", "25mg", "50mg"],          "oral"),
]

ORDER_TYPES = ["ordered", "verified", "administered", "hold", "discontinued", "renewal", "dose_change", "resume", "taper", "stat"]
MEDICATION_LIFECYCLE = ["ordered", "verified", "administered", "hold", "discontinued"]
CLAIM_LIFECYCLE = ["submitted", "pending", "denied", "appealed", "approved", "paid"]
ADT_LIFECYCLE = ["admit", "transfer", "discharge"]

ALLERGY_SUBSTANCES = [
    "Penicillin", "Peanuts", "Latex", "Shellfish", "Iodinated contrast",
    "Sulfa drugs", "Aspirin", "ACE inhibitors", "Bee venom", "Morphine",
]
ALLERGY_REACTIONS = [
    "rash", "hives", "anaphylaxis", "angioedema", "bronchospasm",
    "nausea", "vomiting", "itching", "wheezing", "hypotension",
]

AUTH_DECISIONS = ["pending", "approved", "denied", "appealed"]
ENCOUNTER_LOCATIONS = [
    "ED", "ICU", "Stepdown", "Telemetry", "MedSurg", "OR", "PACU", "Rehab",
]

PATIENT_ENCOUNTER_STATE: dict[str, dict[str, str | int]] = {}
PATIENT_CLAIM_STATE: dict[str, dict[str, str | int | float]] = {}
PATIENT_MEDICATION_STATE: dict[str, dict[str, str | int | list[str]]] = {}
PENDING_FOLLOWUPS: list[tuple[str, dict]] = []


def adt_event():
    patient = choose_patient_id()
    provider = choose_provider_id()
    state = PATIENT_ENCOUNTER_STATE.get(patient)
    if not state or state.get("phase") == "discharge":
        state = {
            "encounter_id": f"enc-{random.randint(1000, 9999)}",
            "phase_idx": 0,
            "location": random.choice(ENCOUNTER_LOCATIONS),
        }
    else:
        phase_idx = int(state.get("phase_idx", 0))
        state["phase_idx"] = min(phase_idx + 1, len(ADT_LIFECYCLE) - 1)
        if ADT_LIFECYCLE[int(state["phase_idx"])] == "transfer":
            state["location"] = random.choice(ENCOUNTER_LOCATIONS)

    phase = ADT_LIFECYCLE[int(state["phase_idx"])]
    PATIENT_ENCOUNTER_STATE[patient] = {**state, "phase": phase}
    diagnosis = random.choice(DIAGNOSES)
    payload = {
        "diagnosis": diagnosis,
        "symptom": random.choice(SYMPTOMS),
        "note": f"ADT update: patient {phase} at {state['location']}.",
        "system": random.choice(EHR_SYSTEMS),
        "icd10_code": random.choice(DIAGNOSIS_CODES),
        "event_family": "ADT",
        "encounter_action": phase,
        "location": state["location"],
    }
    event = event_envelope(
        "ADTSystem",
        "EHR",
        "CLINICAL_NOTE",
        patient,
        str(state["encounter_id"]),
        provider,
        payload,
    )
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["EHR"], event


def allergy_intolerance_event():
    patient = choose_patient_id()
    diagnosis = random.choice(["Allergy", "Drug Intolerance", "Adverse Drug Reaction"])
    symptom = random.choice(ALLERGY_REACTIONS)
    payload = {
        "diagnosis": diagnosis,
        "symptom": symptom,
        "note": f"Allergy/intolerance update: reaction {symptom} to {random.choice(ALLERGY_SUBSTANCES)}.",
        "system": random.choice(EHR_SYSTEMS),
        "icd10_code": random.choice(DIAGNOSIS_CODES),
        "event_family": "ALLERGY_INTOLERANCE",
        "allergen": random.choice(ALLERGY_SUBSTANCES),
        "reaction_severity": random.choice(["mild", "moderate", "severe"]),
    }
    event = event_envelope(
        random.choice(EHR_SYSTEMS),
        "EHR",
        "CLINICAL_NOTE",
        patient,
        f"enc-{random.randint(1000,9999)}",
        choose_provider_id(),
        payload,
    )
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["EHR"], event


def problem_list_update_event():
    patient = choose_patient_id()
    diagnosis = random.choice(DIAGNOSES)
    action = random.choice(["add", "update", "resolve"])
    payload = {
        "diagnosis": diagnosis,
        "symptom": random.choice(SYMPTOMS),
        "note": f"Problem-list {action} for {diagnosis}.",
        "system": random.choice(EHR_SYSTEMS),
        "icd10_code": random.choice(DIAGNOSIS_CODES),
        "event_family": "PROBLEM_LIST_UPDATE",
        "problem_action": action,
    }
    event = event_envelope(
        random.choice(EHR_SYSTEMS),
        "EHR",
        "CLINICAL_NOTE",
        patient,
        f"enc-{random.randint(1000,9999)}",
        choose_provider_id(),
        payload,
    )
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["EHR"], event


def medication_administration_event(patient_id: str | None = None, force_state: str | None = None):
    patient = patient_id or choose_patient_id()
    med_name, drug_class, doses, default_route = random.choice(MEDICATIONS)
    lifecycle_state = force_state or random.choice(MEDICATION_LIFECYCLE)
    payload = {
        "medication": med_name,
        "drug_class": drug_class,
        "dose": random.choice(doses),
        "route": default_route,
        "frequency": random.choice(["once", "every 6 hours", "every 8 hours", "daily"]),
        "order_type": lifecycle_state,
        "days_supply": random.choice([1, 3, 7, 14, 30]),
        "event_family": "MEDICATION_ADMINISTRATION",
        "administration_status": lifecycle_state,
        "administration_site": random.choice(["inpatient", "outpatient", "home"]) if lifecycle_state == "administered" else None,
        "administered_by": choose_provider_id() if lifecycle_state == "administered" else None,
    }
    event = event_envelope(
        "eMAR",
        "PHARMACY",
        "MEDICATION_ORDER",
        patient,
        f"enc-{random.randint(1000,9999)}",
        choose_provider_id(),
        payload,
    )
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["PHARMACY"], event


def medication_lifecycle_event(patient_id: str | None = None):
    patient = patient_id or choose_patient_id()
    state = PATIENT_MEDICATION_STATE.get(patient)
    if not state or int(state.get("idx", 0)) >= len(MEDICATION_LIFECYCLE) - 1:
        med_name, drug_class, doses, default_route = random.choice(MEDICATIONS)
        state = {
            "order_id": f"med-order-{uuid.uuid4()}",
            "idx": 0,
            "medication": med_name,
            "drug_class": drug_class,
            "doses": doses,
            "route": default_route,
            "encounter_id": f"enc-{random.randint(1000,9999)}",
        }
    else:
        state["idx"] = int(state.get("idx", 0)) + 1

    lifecycle_state = MEDICATION_LIFECYCLE[int(state["idx"])]
    PATIENT_MEDICATION_STATE[patient] = state
    payload = {
        "medication": state["medication"],
        "drug_class": state["drug_class"],
        "dose": random.choice(state["doses"]),
        "route": state["route"],
        "frequency": random.choice(["once", "every 6 hours", "every 8 hours", "daily"]),
        "order_type": lifecycle_state,
        "days_supply": random.choice([1, 3, 7, 14, 30]),
        "event_family": "MEDICATION_LIFECYCLE",
        "medication_order_id": state["order_id"],
        "lifecycle_status": lifecycle_state,
        "administered_by": choose_provider_id() if lifecycle_state == "administered" else None,
    }
    event = event_envelope(
        "Pharmacy",
        "PHARMACY",
        "MEDICATION_ORDER",
        patient,
        str(state["encounter_id"]),
        choose_provider_id(),
        payload,
    )
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["PHARMACY"], event


def prior_auth_decision_event(patient_id: str | None = None):
    patient = patient_id or choose_patient_id()
    proc_code, proc_desc = random.choice(PROCEDURE_CODES)
    decision = random.choice(AUTH_DECISIONS)
    amount = round(random.uniform(80, 15000), 2)
    payload = {
        "claim_id": f"priorauth-{uuid.uuid4()}",
        "payer": random.choice(PAYERS),
        "procedure_code": proc_code,
        "procedure_description": proc_desc,
        "diagnosis_code": random.choice(DIAGNOSIS_CODES),
        "billed_amount": amount,
        "allowed_amount": round(amount * random.uniform(0.3, 1.0), 2),
        "status": decision,
        "claim_type": random.choice(["professional", "pharmacy", "institutional"]),
        "service_date": fake.date_between(start_date="-60d", end_date="today").isoformat(),
        "event_family": "PRIOR_AUTH_DECISION",
        "auth_decision": decision,
    }
    event = event_envelope("UtilizationManagement", "CLAIMS", "CLAIM_STATUS", patient, None, None, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["CLAIMS"], event


def procedure_performed_event(patient_id: str | None = None):
    patient = patient_id or choose_patient_id()
    proc_code, proc_desc = random.choice(PROCEDURE_CODES)
    amount = round(random.uniform(100, 20000), 2)
    payload = {
        "claim_id": f"proc-{uuid.uuid4()}",
        "payer": random.choice(PAYERS),
        "procedure_code": proc_code,
        "procedure_description": proc_desc,
        "diagnosis_code": random.choice(DIAGNOSIS_CODES),
        "billed_amount": amount,
        "allowed_amount": round(amount * random.uniform(0.4, 1.0), 2),
        "status": random.choice(["approved", "submitted", "pending"]),
        "claim_type": random.choice(["professional", "institutional"]),
        "service_date": fake.date_between(start_date="-30d", end_date="today").isoformat(),
        "event_family": "PROCEDURE_PERFORMED",
        "procedure_status": "performed",
    }
    event = event_envelope("ProcedureSystem", "CLAIMS", "CLAIM_STATUS", patient, f"enc-{random.randint(1000,9999)}", choose_provider_id(), payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["CLAIMS"], event


def claim_lifecycle_event(patient_id: str | None = None):
    patient = patient_id or choose_patient_id()
    state = PATIENT_CLAIM_STATE.get(patient)
    if not state or int(state.get("idx", 0)) >= len(CLAIM_LIFECYCLE) - 1:
        proc_code, proc_desc = random.choice(PROCEDURE_CODES)
        amount = round(random.uniform(60, 14000), 2)
        state = {
            "claim_id": f"claim-{uuid.uuid4()}",
            "idx": 0,
            "procedure_code": proc_code,
            "procedure_description": proc_desc,
            "diagnosis_code": random.choice(DIAGNOSIS_CODES),
            "payer": random.choice(PAYERS),
            "billed_amount": amount,
        }
    else:
        state["idx"] = int(state.get("idx", 0)) + 1

    status = CLAIM_LIFECYCLE[int(state["idx"])]
    PATIENT_CLAIM_STATE[patient] = state
    payload = {
        "claim_id": state["claim_id"],
        "payer": state["payer"],
        "procedure_code": state["procedure_code"],
        "procedure_description": state["procedure_description"],
        "diagnosis_code": state["diagnosis_code"],
        "billed_amount": state["billed_amount"],
        "allowed_amount": round(float(state["billed_amount"]) * random.uniform(0.4, 1.0), 2),
        "status": status,
        "claim_type": random.choice(["professional", "institutional", "pharmacy"]),
        "service_date": fake.date_between(start_date="-90d", end_date="today").isoformat(),
        "event_family": "CLAIM_LIFECYCLE",
        "lifecycle_status": status,
    }
    event = event_envelope("ClaimsSystem", "CLAIMS", "CLAIM_STATUS", patient, None, None, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["CLAIMS"], event


def pharmacy_event():
    patient = choose_patient_id()
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
    event = event_envelope("Pharmacy", "PHARMACY", "MEDICATION_ORDER", patient, f"enc-{random.randint(1000,9999)}", choose_provider_id(), payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["PHARMACY"], event


PAYERS = [
    "Aetna", "United", "BCBS", "Medicare", "Medicaid", "Cigna", "Humana", "Kaiser", "Tricare", "Centene",
    "Anthem", "Molina", "WellCare", "CareFirst", "Highmark", "Health Net", "Oscar", "Tufts Health Plan", "UPMC Health Plan", "EmblemHealth",
]

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
    # Additional E&M / inpatient
    ("99223", "Initial hospital care, high complexity"),
    ("99233", "Subsequent hospital care, high complexity"),
    ("99291", "Critical care, first 30-74 minutes"),
    ("99406", "Smoking and tobacco cessation counseling"),
    # Additional lab/diagnostics
    ("82962", "Glucose, blood by glucose monitoring device"),
    ("84443", "Thyroid stimulating hormone"),
    ("83880", "Natriuretic peptide"),
    ("85730", "Partial thromboplastin time"),
    # Additional cardiac/imaging
    ("92928", "Percutaneous coronary intervention with stent"),
    ("93970", "Duplex scan of extremity veins, complete bilateral"),
    ("71260", "CT thorax with contrast"),
    ("76700", "Ultrasound, abdominal, complete"),
    # Additional procedures
    ("36556", "Insertion of non-tunneled central venous catheter"),
    ("31500", "Emergency endotracheal intubation"),
    ("92950", "Cardiopulmonary resuscitation"),
    ("11042", "Debridement, subcutaneous tissue"),
    ("20610", "Arthrocentesis, major joint"),
    ("11721", "Debridement of nails"),
]

DIAGNOSIS_CODES = [
    "I10", "E11.9", "J18.9", "J44.1", "N18.3", "I48.91", "E03.9", "D64.9", "K21.0", "I50.9",
    "I25.10", "N17.9", "E87.1", "E87.0", "E87.6", "F41.9", "F32.9", "G47.33", "R07.9", "M79.1",
]


def claims_event():
    patient = choose_patient_id()
    proc_code, proc_desc = random.choice(PROCEDURE_CODES)
    amount = round(random.uniform(50, 12000), 2)
    status = random.choice(["submitted", "pending", "denied", "appealed", "adjudicated", "approved", "paid"])
    payload = {
        "claim_id": f"claim-{uuid.uuid4()}",
        "payer": random.choice(PAYERS),
        "procedure_code": proc_code,
        "procedure_description": proc_desc,
        "diagnosis_code": random.choice(DIAGNOSIS_CODES),
        "billed_amount": amount,
        "allowed_amount": round(amount * random.uniform(0.4, 1.0), 2),
        "status": status,
        "claim_type": random.choice(["professional", "institutional", "dental", "pharmacy"]),
        "service_date": fake.date_between(start_date="-90d", end_date="today").isoformat(),
        "event_family": "CLAIM_LIFECYCLE",
        "lifecycle_status": status,
    }
    event = event_envelope("ClaimsSystem", "CLAIMS", "CLAIM_STATUS", patient, None, None, payload)
    event, _ = apply_temporal_noise(event, payload)
    return TOPICS["CLAIMS"], event


def patient_reference_event():
    patient = choose_patient_id()
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
    provider = choose_provider_id()
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
    device_id = f"device-{random.randint(1, DEVICE_POOL_SIZE)}"
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


REFERENCE_GENERATORS = [
    patient_reference_event,
    provider_reference_event,
    device_reference_event,
    medication_reference_event,
    payer_reference_event,
]

GENERATORS = [
    ehr_event,
    adt_event,
    allergy_intolerance_event,
    problem_list_update_event,
    lab_event,
    device_event,
    pharmacy_event,
    medication_administration_event,
    medication_lifecycle_event,
    claim_lifecycle_event,
    claims_event,
    prior_auth_decision_event,
    procedure_performed_event,
]


def _interval_event_counts() -> tuple[int, int]:
    tx_count = TRANSACTION_EVENTS_PER_INTERVAL
    ref_count = REFERENCE_EVENTS_PER_INTERVAL
    hour = datetime.now(timezone.utc).hour
    if hour in SHIFT_HANDOFF_HOURS and random.random() < BATCH_BURST_PROBABILITY:
        tx_count *= BATCH_BURST_MULTIPLIER
        ref_count *= max(1, BATCH_BURST_MULTIPLIER // 2)
    return tx_count, ref_count


wait_for_schema_registry()
register_schema()
avro_serializer = build_avro_serializer()


def _on_delivery(err, msg):
    if err is not None:
        print(f"Delivery failed for {msg.topic() if msg else '?'}: {err}")


def _next_event_with_type_diversity(seen_event_types: set[str], generators):
    # Try to avoid duplicate event types in the same interval batch.
    for _ in range(10):
        generator = random.choice(generators)
        topic, event = generator()
        if event["event_type"] not in seen_event_types:
            return topic, event
    return random.choice(generators)()


def _emit_event(topic: str, event: dict):
    key = event["patient_id"] or event["event_id"]
    avro_payload = avro_serializer(event, SerializationContext(topic, MessageField.VALUE))
    producer.produce(topic, key=key.encode("utf-8"), value=avro_payload, on_delivery=_on_delivery)
    print(f"Produced {event['event_type']} to {topic}: {event['event_id']}")


while True:
    produced_types: set[str] = set()
    tx_count, ref_count = _interval_event_counts()

    for _ in range(tx_count):
        topic, event = _next_event_with_type_diversity(produced_types, GENERATORS)
        produced_types.add(event["event_type"])
        _emit_event(topic, event)

    while PENDING_FOLLOWUPS:
        topic, event = PENDING_FOLLOWUPS.pop(0)
        produced_types.add(event["event_type"])
        _emit_event(topic, event)

    for _ in range(ref_count):
        topic, event = _next_event_with_type_diversity(produced_types, REFERENCE_GENERATORS)
        produced_types.add(event["event_type"])
        _emit_event(topic, event)

    producer.flush()
    time.sleep(INTERVAL)
