# Kafka Schema And Topic Design

## Overview

The streaming layer uses a single logical envelope schema for all events and differentiates event semantics through topic choice, `event_type`, and the JSON content stored in `payload_json`.

This keeps the MVP simple while still documenting a clear event contract for future hardening.

## Envelope Schema

The Avro envelope is defined in `schemas/medical_event.avsc`.

| Field | Type | Meaning |
| --- | --- | --- |
| `event_id` | `string` | Globally unique event identifier |
| `event_ts` | `string` | Event timestamp in ISO-8601 form |
| `source_system` | `string` | Producing system name |
| `source_type` | `string` | Broad source family such as `EHR`, `LAB`, `DEVICE`, `PHARMACY`, `CLAIMS`, or `REFERENCE` |
| `event_type` | `string` | Domain event classification |
| `patient_id` | `null or string` | Patient identifier when applicable |
| `encounter_id` | `null or string` | Encounter identifier when applicable |
| `provider_id` | `null or string` | Provider identifier when applicable |
| `payload_json` | `string` | Event-specific JSON payload |
| `schema_version` | `string` | Schema version marker, currently `1.0.0` |

## Wire Format Behavior

Current MVP behavior:

- the producer registers the Avro envelope in Schema Registry,
- messages are still published to Kafka as JSON strings,
- consumers decode JSON directly rather than using an Avro deserializer.

This is an intentional local-development tradeoff. It improves readability and reduces ceremony in the Python processor while preserving a documented contract.

## Topic Topology

### Transactional Topics

| Topic | Partitions | Event Type | Typical Producer |
| --- | --- | --- | --- |
| `healthcare.ehr.events` | 3 | `CLINICAL_NOTE` | Epic or Cerner simulation |
| `healthcare.lab.results` | 3 | `LAB_RESULT` | LIS simulation |
| `healthcare.device.telemetry` | 3 | `VITAL_SIGN` | device telemetry simulation |
| `healthcare.pharmacy.orders` | 3 | `MEDICATION_ORDER` | pharmacy simulation |
| `healthcare.claims.events` | 3 | `CLAIM_STATUS` | claims simulation |

### Reference Topics

| Topic | Partitions | Event Type | Purpose |
| --- | --- | --- | --- |
| `healthcare.master.patients` | 1 | `PATIENT_MASTER_UPSERT` | patient demographics and risk tier |
| `healthcare.master.providers` | 1 | `PROVIDER_MASTER_UPSERT` | provider specialty and organization |
| `healthcare.master.devices` | 1 | `DEVICE_MASTER_UPSERT` | device model and vendor metadata |
| `healthcare.master.medications` | 1 | `MEDICATION_MASTER_UPSERT` | drug class and safety tier |
| `healthcare.master.payers` | 1 | `PAYER_MASTER_UPSERT` | plan type and region |

### Reserved Topic

| Topic | Partitions | Status |
| --- | --- | --- |
| `healthcare.dlq.events` | 1 | created for future dead-letter handling |

## Producer Keying Strategy

Messages are produced with key:

- `patient_id` when present,
- otherwise `event_id`.

Consequences:

- patient-scoped transactional events tend to preserve partition affinity,
- reference events without patient identifiers fall back to event-level uniqueness,
- ordering is only guaranteed per partition and key, not globally.

## Event Payload Shapes

### Clinical Note Payload

```json
{
  "diagnosis": "Pneumonia",
  "symptom": "cough",
  "note": "Patient presents with cough. Assessment suggests Pneumonia.",
  "system": "Epic"
}
```

### Lab Result Payload

```json
{
  "lab_name": "Potassium",
  "value": 6.2,
  "unit": "mmol/L",
  "abnormal": true
}
```

### Device Telemetry Payload

```json
{
  "device_id": "device-1",
  "heart_rate": 124,
  "spo2": 91,
  "systolic_bp": 148,
  "diastolic_bp": 92
}
```

### Medication Order Payload

```json
{
  "medication": "Warfarin",
  "dose": "5mg",
  "route": "oral",
  "frequency": "daily"
}
```

### Claim Status Payload

```json
{
  "claim_id": "claim-uuid",
  "payer": "Aetna",
  "procedure_code": "99213",
  "status": "approved"
}
```

### Patient Reference Payload

```json
{
  "patient_id": "patient-0001",
  "name": "Jane Doe",
  "sex": "F",
  "age": 67,
  "risk_tier": "high"
}
```

### Provider Reference Payload

```json
{
  "provider_id": "provider-001",
  "name": "Dr. Alex Smith",
  "specialty": "Cardiology",
  "organization": "City Hospital"
}
```

### Device Reference Payload

```json
{
  "device_id": "device-7",
  "model": "CardioMon-100",
  "vendor": "MedTech",
  "device_type": "monitor"
}
```

### Medication Reference Payload

```json
{
  "medication": "Metformin",
  "drug_class": "Antidiabetic",
  "safety_tier": "monitor"
}
```

### Payer Reference Payload

```json
{
  "payer": "BCBS",
  "plan_type": "PPO",
  "region": "Northeast"
}
```

## Enrichment Contract

Reference events are not materialized as a separate downstream output stream. Instead, the processor keeps them in memory and merges the matching records into transactional payloads as:

```json
"reference_data": {
  "patient": {...},
  "provider": {...},
  "device": {...},
  "medication": {...},
  "payer": {...}
}
```

This enrichment affects both:

- the clinical text rendered for vector indexing,
- the properties and relationships written into Neo4j.

## Schema Registry Behavior

The producer attempts to register the same Avro envelope under all topic-value subjects:

- transactional topic subjects,
- reference topic subjects.

In a stricter production implementation, consider:

- using dedicated schemas per event family,
- evolving payload structure through strongly typed nested Avro records,
- enforcing compatibility mode,
- validating producer and consumer compatibility in CI.

## Production Hardening Recommendations

- switch to Confluent Avro or Protobuf serialization on the wire,
- separate transactional and master-data schema families,
- add DLQ publishing for malformed payloads and enrichment failures,
- include explicit trace, tenant, and lineage metadata,
- implement idempotent producer settings and stronger replay controls.
