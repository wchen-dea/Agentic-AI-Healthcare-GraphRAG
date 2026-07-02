# Kafka Schema And Topic Design

## Purpose

This document defines the event contract, topic topology, and runtime usage patterns for the healthcare streaming layer.

The stack uses one shared envelope schema and topic-based routing semantics.

## Envelope Schema

Source file: schemas/medical_event.avsc

| Field | Type | Description |
| --- | --- | --- |
| event_id | string | Unique event identifier |
| event_ts | string | ISO-8601 timestamp |
| source_system | string | Originating system name |
| source_type | string | Source class: EHR, LAB, DEVICE, PHARMACY, CLAIMS, REFERENCE |
| event_type | string | Domain-level event classification |
| patient_id | null or string | Patient identifier if applicable |
| encounter_id | null or string | Encounter identifier if applicable |
| provider_id | null or string | Provider identifier if applicable |
| payload_json | string | Event-specific JSON payload |
| schema_version | string | Envelope schema version, default 1.0.0 |

## Schema Registry Behavior

Producer behavior in producer/produce_events.py:

- Registers the Avro envelope under topic-value subjects for transactional and reference topics.
- Uses POST /subjects/{subject}/versions.
- Serializes values with Confluent AvroSerializer using subject resolution from topic context.

Operational implication:

- Contract is enforced through Schema Registry subjects.
- Kafka value payloads carry Confluent wire framing (magic byte + schema ID + Avro binary payload).

## Wire Format

Current producer wire encoding:

- key: UTF-8 bytes from patient_id when present, otherwise event_id
- value: Confluent Avro binary payload with schema ID from Schema Registry

Current consumers deserialize values with Confluent AvroDeserializer and then parse payload_json for domain details.

## Conduktor Display And Masking Notes

If Conduktor topic view is set to `Bytes` for value deserialization, Avro payloads cannot be decoded for field-level operations.

Use this Conduktor setup for this project:

- Key deserializer: `String`
- Value deserializer: `Avro (Schema Registry)`
- Schema Registry URL: `http://schema-registry:8081`

Common error:

- `Message cannot be displayed. The data masking rules cannot be applied with bytes deserializer.`

Root cause:

- Value deserializer is `Bytes` instead of `Avro`.

Fix:

1. Switch topic value deserializer to `Avro (Schema Registry)`.
1. Refresh topic view.
1. Reopen messages.

Important limitation in current schema design:

- `payload_json` is defined as a `string` field in `schemas/medical_event.avsc`.
- Field-level masking can apply to top-level envelope fields.
- Field-level masking cannot target nested JSON attributes inside `payload_json` unless that payload is migrated to structured Avro fields.

## Topic Topology

### Transactional Topics

| Topic | Partitions | Typical Event Type | Producer Function |
| --- | --- | --- | --- |
| healthcare.ehr.events | 3 | CLINICAL_NOTE | ehr_event |
| healthcare.lab.results | 3 | LAB_RESULT | lab_event |
| healthcare.device.telemetry | 3 | VITAL_SIGN | device_event |
| healthcare.pharmacy.orders | 3 | MEDICATION_ORDER | pharmacy_event |
| healthcare.claims.events | 3 | CLAIM_STATUS | claims_event |

### Reference Topics

| Topic | Partitions | Typical Event Type | Producer Function |
| --- | --- | --- | --- |
| healthcare.master.patients | 1 | PATIENT_MASTER_UPSERT | patient_reference_event |
| healthcare.master.providers | 1 | PROVIDER_MASTER_UPSERT | provider_reference_event |
| healthcare.master.devices | 1 | DEVICE_MASTER_UPSERT | device_reference_event |
| healthcare.master.medications | 1 | MEDICATION_MASTER_UPSERT | medication_reference_event |
| healthcare.master.payers | 1 | PAYER_MASTER_UPSERT | payer_reference_event |

### Reserved Topic

| Topic | Partitions | Current Status |
| --- | --- | --- |
| healthcare.dlq.events | 1 | Created by kafka-init; not currently written by processor |

## Topic Creation And Lifecycle

Topics are explicitly created by kafka-init in docker-compose.yml with auto-create disabled on the broker.

This ensures deterministic local topology and avoids accidental topic drift.

## Event Generation Mix

The producer loop emits:

- 80 percent transactional events
- 20 percent reference events

This ratio is controlled by random selection in producer/produce_events.py.

## Payload Shape Examples

### Clinical Note

```json
{
  "diagnosis": "Pneumonia",
  "symptom": "cough",
  "note": "Patient presents with cough. Assessment suggests Pneumonia.",
  "system": "Epic",
  "icd10_code": "J18.9"
}
```

### Lab Result

The producer selects from 18 lab tests. Each test carries a per-test abnormality threshold evaluated by the Flink processor to write `MAY_INDICATE` edges.

```json
{
  "lab_name": "Potassium",
  "value": 6.2,
  "unit": "mmol/L",
  "abnormal": true,
  "lab_panel": "BMP",
  "specimen_type": "serum"
}
```

Additional lab examples (same schema):

| lab_name | unit | Abnormal condition triggered |
| --- | --- | --- |
| Glucose | mg/dL | ≥ 180 → Hyperglycemia |
| HbA1c | % | ≥ 6.5 → Diabetes Mellitus |
| Creatinine | mg/dL | > 1.2 → Chronic Kidney Disease |
| eGFR | mL/min | < 60 → Chronic Kidney Disease |
| Troponin I | ng/mL | > 0.04 → Acute Myocardial Infarction |
| WBC | 10³/µL | > 11.0 → Infection |
| INR | ratio | > 3.0 → Anticoagulation Concern |
| LDL | mg/dL | > 130 → Hyperlipidemia |
| TSH | mIU/L | > 4.5 → Hypothyroidism / < 0.5 → Hyperthyroidism |
| Hemoglobin | g/dL | < 12.0 → Anemia |
| Sodium | mmol/L | < 135 → Hyponatremia / > 145 → Hypernatremia |

### Device Telemetry

Device events now include temperature, respiratory rate, optional glucose, device type, and an alert field for threshold-breach conditions.

```json
{
  "device_id": "device-7",
  "device_type": "bedside",
  "heart_rate": 121,
  "spo2": 91,
  "systolic_bp": 150,
  "diastolic_bp": 95,
  "temperature_c": 38.6,
  "respiratory_rate": 22,
  "glucose_mg_dl": null,
  "alert": "tachycardia"
}
```

Possible `alert` values: `tachycardia`, `hypoxia`, `hypertension`, `bradycardia`, or `null` (no alert).
Possible `device_type` values: `monitor`, `wearable`, `bedside`, `implant`, `patch`.

### Medication Order

The producer selects from 24 medications. Each order carries `drug_class` (derived from the medication catalog), `order_type`, and `days_supply`.

```json
{
  "medication": "Warfarin",
  "drug_class": "Anticoagulant",
  "dose": "5mg",
  "route": "oral",
  "frequency": "daily",
  "order_type": "new",
  "days_supply": 30
}
```

Possible `order_type` values: `new`, `renewal`, `discontinue`, `dose_change`.
Possible `route` values: `oral`, `IV`, `subcutaneous`, `inhaled`, `topical`, `sublingual`.

### Claim Event

Claims now carry a full financial record including procedure description (from 19 CPT codes), ICD-10 diagnosis code, financial amounts, claim type, and service date.

```json
{
  "claim_id": "claim-<uuid>",
  "payer": "Aetna",
  "procedure_code": "99213",
  "procedure_description": "Office visit, established patient, moderate",
  "diagnosis_code": "I10",
  "billed_amount": 285.00,
  "allowed_amount": 142.50,
  "claim_type": "professional",
  "service_date": "2026-06-15",
  "status": "approved"
}
```

Possible `status` values: `submitted`, `approved`, `denied`, `pending`, `appealed`, `partially_approved`.
Possible `claim_type` values: `professional`, `institutional`, `dental`, `pharmacy`.
Hospital-related CPT codes (99232, 99285, 99291, 99223) trigger a `(Claim)-[:RESULTED_IN]->(AdverseOutcome {code: "HO"})` edge in Neo4j.

### Reference (Patient)

```json
{
  "patient_id": "patient-0001",
  "name": "Jane Doe",
  "sex": "F",
  "age": 67,
  "risk_tier": "high"
}
```

### Reference (Provider)

```json
{
  "provider_id": "provider-001",
  "name": "Dr. Alice Chen",
  "specialty": "Cardiology",
  "organization": "City Hospital",
  "npi": "1234567890"
}
```

### Reference (Device)

```json
{
  "device_id": "device-5",
  "model": "CardioMon-100",
  "vendor": "MedTech",
  "device_type": "monitor",
  "firmware_version": "2.1.04",
  "connectivity": "WiFi"
}
```

### Reference (Medication)

```json
{
  "medication": "Warfarin",
  "drug_class": "Anticoagulant",
  "safety_tier": "high-alert",
  "requires_monitoring": true,
  "controlled_substance": false
}
```

### Reference (Payer)

```json
{
  "payer": "Aetna",
  "plan_type": "PPO",
  "region": "Northeast",
  "network_tier": "in-network"
}
```

## Enrichment Contract

The processor keeps reference records in memory and injects matched data into transactional payloads under payload.reference_data:

```json
{
  "reference_data": {
    "patient": {},
    "provider": {},
    "device": {},
    "medication": {},
    "payer": {}
  }
}
```

Impacts:

- Enriched context contributes to rendered text persisted in Qdrant.
- Enriched fields contribute to node and relationship updates in Neo4j.
- reference_hit_count tracks number of matched reference entities.

## Consumer Groups And Offsets

Active PyFlink job behavior:

- One KafkaSource is created per topic.
- Group ID is generated as FLINK_KAFKA_GROUP_ID-topic-name.
- Source starts from earliest offsets.

Consequences:

- First run and replay-friendly restarts process full topic history.
- Per-topic group IDs isolate offsets by topic and avoid accidental cross-topic coupling.

## Data Quality And Hardening Recommendations

Recommended next steps:

- Enforce Schema Registry compatibility mode explicitly per subject (for example backward or full).
- Add producer-side payload validation and schema evolution tests in CI.
- Implement DLQ writes for parse, enrich, or sink failures.
- Add explicit event lineage metadata (trace_id, tenant_id, producer_version).
- Add replay governance for large topic retention scenarios.
- Consider schema v2 with structured payload records (instead of `payload_json` string) for stronger validation and finer masking controls.
