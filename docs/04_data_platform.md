# Kafka Schema And Topic Design

## Purpose

This document defines the event contract, topic topology, and runtime usage patterns for the healthcare streaming layer.

The stack uses one shared envelope schema and topic-based routing semantics.

## Envelope Schema

Source file: data-platform/healthcare/schemas/medical_event.avsc

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

Producer behavior in data-platform/healthcare/producer/produce_events.py:

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
2. Refresh topic view.
3. Reopen messages.

Important limitation in current schema design:

- `payload_json` is defined as a `string` field in `data-platform/healthcare/schemas/medical_event.avsc`.
- Field-level masking can apply to top-level envelope fields.
- Field-level masking cannot target nested JSON attributes inside `payload_json` unless that payload is migrated to structured Avro fields.

## Topic Topology

### Transactional Topics

| Topic | Partitions | Typical Event Type | Producer Function |
| --- | --- | --- | --- |
| healthcare.ehr.events | 3 | CLINICAL_NOTE | ehr_event plus ADT, allergy/intolerance, and problem-list generators |
| healthcare.lab.results | 3 | LAB_RESULT | lab_event |
| healthcare.device.telemetry | 3 | VITAL_SIGN | device_event |
| healthcare.pharmacy.orders | 3 | MEDICATION_ORDER | pharmacy_event plus medication admin/lifecycle generators |
| healthcare.claims.events | 3 | CLAIM_STATUS | claims_event plus claim lifecycle, prior-auth, and procedure-performed generators |

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

## Supply Chain Topics (parallel domain)

Created by `supplychain-kafka-init` when the supply-chain overlay is active.

### Supply Chain Transactional Topics

| Topic | Partitions | Typical Event Type | Producer Function |
| --- | --- | --- | --- |
| supplychain.purchase.orders | 3 | PURCHASE_ORDER | purchase_order_event |
| supplychain.shipment.updates | 3 | SHIPMENT_UPDATE | shipment_update_event |
| supplychain.quality.results | 3 | QUALITY_RESULT | quality_result_event |
| supplychain.disruption.alerts | 3 | DISRUPTION_ALERT | disruption_alert_event |
| supplychain.inventory.levels | 3 | INVENTORY_LEVEL | inventory_level_event |

### Supply Chain Reference Topics

| Topic | Partitions | Typical Event Type | Producer Function |
| --- | --- | --- | --- |
| supplychain.master.suppliers | 1 | SUPPLIER_MASTER_UPSERT | supplier_reference_event |
| supplychain.master.parts | 1 | PART_MASTER_UPSERT | part_reference_event |
| supplychain.master.facilities | 1 | FACILITY_MASTER_UPSERT | facility_reference_event |

### Supply Chain Envelope Schema

Source file: `data-platform/supply-chain/schemas/supply_chain_event.avsc`. Uses entity_id/facility_id/supplier_id instead of patient_id/encounter_id/provider_id.

## Topic Creation And Lifecycle

Topics are explicitly created by kafka-init in container/docker-compose.healthcare.yml with auto-create disabled on the broker.

This ensures deterministic local topology and avoids accidental topic drift.

## Event Generation Mix

The producer loop now emits both categories every interval tick:

- transactional events per tick: `TRANSACTION_EVENTS_PER_INTERVAL` (default `3`)
- reference events per tick: `REFERENCE_EVENTS_PER_INTERVAL` (default `3`)

Default behavior represents a 200% increase baseline for each category relative to the prior single-event-per-interval stream.

Within each interval batch, the producer attempts to emit distinct `event_type` values.
Shift-handoff windows can introduce burst traffic (`BATCH_BURST_PROBABILITY`, `BATCH_BURST_MULTIPLIER`, `SHIFT_HANDOFF_HOURS`) to better emulate operational load spikes.

Temporal and operational realism features:
- Late-arriving events via backdated `event_ts` (`late_arrival_minutes` in payload)
- Correction events via `is_correction` and `correction_of_event_id`
- Correlated follow-up events from critical abnormal labs to medication administration actions

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

The producer selects from 36 lab tests. Each test carries a per-test abnormality threshold evaluated by the Flink processor to write `MAY_INDICATE` edges.

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

The producer selects from 48 medications. Each order carries `drug_class` (derived from the medication catalog), `order_type`, and `days_supply`.

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

Possible `order_type` values include baseline order actions (`renewal`, `dose_change`, `resume`, `taper`, `stat`) and lifecycle states (`ordered`, `verified`, `administered`, `hold`, `discontinued`).
Possible `route` values: `oral`, `IV`, `subcutaneous`, `inhaled`, `topical`, `sublingual`.

### Claim Event

Claims now carry a full financial record including procedure description (from 36 CPT codes), ICD-10 diagnosis code, financial amounts, claim type, and service date.

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

Possible `status` values include lifecycle and adjudication states: `submitted`, `pending`, `denied`, `appealed`, `adjudicated`, `approved`, `paid`.
Possible `claim_type` values: `professional`, `institutional`, `dental`, `pharmacy`.
Dedicated claim lifecycle emissions follow `submitted -> pending -> denied -> appealed -> approved -> paid` for longitudinal claim progression.
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
# Neo4j Healthcare Graph Model

## Purpose

Neo4j stores explicit relationship context used by the GraphRAG API to augment vector retrieval with patient-centric graph evidence.

The model prioritizes traceability, simple traversal patterns, and deterministic merges for local replay.

## Graph Principles

- Patient-centric traversal: most queries begin at Patient.
- Event lineage retained through ClinicalEvent and SourceSystem.
- Domain entities merged idempotently from streaming input.
- Reference-data enrichment updates properties and links over time.

## Core Labels

| Label | Meaning |
| --- | --- |
| Patient | Canonical patient node |
| Encounter | Encounter scope for events when present |
| ClinicalEvent | Event lineage record |
| SourceSystem | Source system identity and type |
| Condition | Clinical diagnosis/condition |
| ICD10Code | ICD-10-CM code for a condition |
| Symptom | Symptom extracted from notes |
| Observation | Lab observation entity |
| Medication | Medication catalog node |
| MedicationOrder | Medication order event node |
| Device | Device catalog node |
| DeviceReading | Telemetry event node |
| Claim | Claims event node |
| Procedure | Procedure catalog node (CPT/ICD-PCS code) |
| AdverseEvent | Detected drug adverse reaction event |
| AdverseOutcome | FAERS clinical outcome (HO, LT, DE, DS, CA, OT) |
| Provider | Provider reference node |
| Payer | Payer reference node |

## Constraints And Seed Data

Initialization in data-platform/healthcare/neo4j/init.cypher creates uniqueness constraints for:

- Patient.id
- Encounter.id
- ClinicalEvent.id
- Observation.id
- MedicationOrder.id
- DeviceReading.id
- Claim.id
- Medication.name
- Condition.name
- Symptom.name
- SourceSystem.name
- Provider.id
- Payer.name
- Device.id
- ICD10Code.code
- Procedure.code
- AdverseEvent.id
- AdverseOutcome.code

Seeded drug interaction relationships:

- (Warfarin)-[:INTERACTS_WITH {risk: bleeding_risk, severity: high}]->(Azithromycin)
- (Warfarin)-[:INTERACTS_WITH {risk: bleeding_risk, severity: high}]->(Aspirin)
- (Warfarin)-[:INTERACTS_WITH {risk: bleeding_risk, severity: high}]->(Fluconazole)
- (Lisinopril)-[:INTERACTS_WITH {risk: hyperkalemia_risk, severity: moderate}]->(Spironolactone)
- (Albuterol)-[:INTERACTS_WITH {risk: bronchospasm_risk, severity: moderate}]->(Metoprolol)
- (Metformin)-[:INTERACTS_WITH {risk: nephrotoxicity_risk, severity: moderate}]->(Vancomycin)

Seeded Condition nodes (aligned with lab signal rules): Hyperkalemia, Hyperglycemia, Diabetes Mellitus, Chronic Kidney Disease, Acute Myocardial Infarction, Anemia, Hyperlipidemia, Hypothyroidism, Hyperthyroidism, Hyponatremia, Hypernatremia, Infection, Anticoagulation Concern, Hypertension, Heart Failure.
Drug safety seed data (FAERS-aligned, from `generated_ontology_seeds.cypher`):

- 6 `AdverseOutcome` nodes: DE, LT, HO, DS, CA, OT
- 41 `INTERACTS_WITH` edges with `risk`, `severity`, and `mechanism` annotations (e.g. Warfarin+Aspirin additive_anticoagulation, Morphine+Gabapentin additive_CNS_depression)
- 46 `HAS_KNOWN_REACTION` edges with MedDRA terms (e.g. Lisinopril→Cough, Atorvastatin→Myalgia, Insulin Glargine→Hypoglycaemia/Confusion)
- 23 `CONTRAINDICATED_FOR` edges with reason and severity (e.g. Metformin→CKD lactic_acidosis_risk, Lisinopril→Hyperkalemia worsens_hyperkalemia, Ibuprofen→Heart Failure NSAID_fluid_retention)
## Base Lineage Pattern

Every transactional event writes the base lineage:

- (ClinicalEvent)-[:ABOUT_PATIENT]->(Patient)
- (ClinicalEvent)-[:FROM_SOURCE]->(SourceSystem)
- Optional (ClinicalEvent)-[:DURING_ENCOUNTER]->(Encounter)

This supports traceability from any downstream clinical assertion back to source event metadata.

## Event-Type Specific Patterns

### CLINICAL_NOTE

Creates/merges:

- Condition by diagnosis (tracks `first_seen_ts`, `last_seen_ts`)
- Symptom by symptom text
- ICD10Code by icd10_code field (optional)

Relationships:

- `(Patient)-[HAS_CONDITION {onset_ts}]->(Condition)` — onset timestamp set on first occurrence
- `(Patient)-[:HAS_SYMPTOM]->(Symptom)`
- `(ClinicalEvent)-[:DOCUMENTS]->(Condition)`
- `(ClinicalEvent)-[:DOCUMENTS]->(Symptom)`
- `(Condition)-[:CODED_AS]->(ICD10Code)` — when icd10_code is present

### LAB_RESULT

Creates/merges:

- Observation by event_id (stores `lab_panel`, `specimen_type`)

Relationships:

- `(Patient)-[:HAS_OBSERVATION]->(Observation)`
- `(ClinicalEvent)-[:DOCUMENTS]->(Observation)`

Derived signal rules (evaluated in `merge_lab_signals` after each write):

| Lab | Threshold | Indicated Condition | Reason |
|-----|-----------|--------------------|---------|
| Potassium | ≥ 5.5 mmol/L | Hyperkalemia | elevated_potassium |
| Glucose | ≥ 180 mg/dL | Hyperglycemia | elevated_glucose |
| HbA1c | ≥ 6.5 % | Diabetes Mellitus | elevated_hba1c |
| Creatinine | > 1.2 mg/dL | Chronic Kidney Disease | elevated_creatinine |
| eGFR | < 60 mL/min | Chronic Kidney Disease | low_egfr |
| Troponin I | > 0.04 ng/mL | Acute Myocardial Infarction | elevated_troponin |
| WBC | > 11.0 10³/µL | Infection | elevated_wbc |
| INR | > 3.0 | Anticoagulation Concern | supratherapeutic_inr |
| LDL | > 130 mg/dL | Hyperlipidemia | elevated_ldl |
| TSH | > 4.5 mIU/L | Hypothyroidism | elevated_tsh |
| TSH | < 0.5 mIU/L | Hyperthyroidism | low_tsh |
| Hemoglobin | < 12.0 g/dL | Anemia | low_hemoglobin |
| Sodium | < 135 mmol/L | Hyponatremia | low_sodium |
| Sodium | > 145 mmol/L | Hypernatremia | high_sodium |

Signal edge: `(Observation)-[:MAY_INDICATE {reason}]->(Condition)`

### VITAL_SIGN

Creates/merges:

- DeviceReading by event_id (stores `heart_rate`, `spo2`, `systolic_bp`, `diastolic_bp`, `temperature_c`, `respiratory_rate`, `glucose_mg_dl`, `alert`)
- Device by device_id (stores `device_type`)

Relationships:

- `(Patient)-[:HAS_DEVICE_READING]->(DeviceReading)`
- `(DeviceReading)-[:MEASURED_BY]->(Device)`
- `(ClinicalEvent)-[:DOCUMENTS]->(DeviceReading)`

### MEDICATION_ORDER

Creates/merges:

- MedicationOrder by event_id (stores `dose`, `route`, `frequency`, `order_type`, `days_supply`)
- Medication by medication name (updates `drug_class` from order payload)

Relationships:

- `(MedicationOrder)-[:ORDERS_MEDICATION]->(Medication)`
- `(Patient)-[:HAS_MEDICATION_ORDER]->(MedicationOrder)`
- `(ClinicalEvent)-[:DOCUMENTS]->(MedicationOrder)`

### CLAIM_STATUS

Creates/merges:

- Claim by claim_id (stores `status`, `claim_type`, `diagnosis_code`, `billed_amount`, `allowed_amount`, `service_date`)
- Procedure by procedure_code (stores `description`) — linked on first occurrence
- Payer by payer name — merged idempotently

Relationships:

- `(Patient)-[:HAS_CLAIM]->(Claim)`
- `(ClinicalEvent)-[:DOCUMENTS]->(Claim)`
- `(Claim)-[:FOR_PROCEDURE]->(Procedure)` — when procedure_code is present
- `(Claim)-[:SUBMITTED_TO]->(Payer)` — when payer is present
- `(Claim)-[:RESULTED_IN]->(AdverseOutcome {code: "HO"})` — when procedure_code is a hospital/ICU CPT code or claim_type is institutional

---

## Drug Safety Patterns

Derived from the [Neo4j Drug Safety industry model](https://neo4j.com/developer/industry-use-cases/life-sciences/medical-care/drug-safety/) and FDA FAERS pharmacovigilance design.

### Adverse Event Detection

`merge_adverse_event_signal` fires after every `CLINICAL_NOTE` write. It checks whether the documented symptom matches a `HAS_KNOWN_REACTION` edge for any medication currently ordered for the patient:

```cypher
MATCH (p:Patient {id: $patient_id})
MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
MATCH (m)-[kr:HAS_KNOWN_REACTION]->(s:Symptom {name: $symptom})
MATCH (ce:ClinicalEvent {id: $source_event_id})
MERGE (ae:AdverseEvent {id: $adverse_event_id})
  ON CREATE SET ae.symptom_name = $symptom, ae.severity = kr.severity, ae.meddra_term = kr.meddra_term
MERGE (p)-[:REPORTED_ADVERSE_REACTION]->(ae)
MERGE (ae)-[:ASSOCIATED_WITH_MEDICATION]->(m)
MERGE (ae)-[:TRIGGERED_BY_EVENT]->(ce)
```

Adverse event edges written:

- `(Patient)-[:REPORTED_ADVERSE_REACTION]->(AdverseEvent)`
- `(AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(Medication)`
- `(AdverseEvent)-[:TRIGGERED_BY_EVENT]->(ClinicalEvent)`
- `(Claim)-[:RESULTED_IN]->(AdverseOutcome)` — for institutional / hospital claims

### Drug Safety Knowledge Graph

Seeded relationship types (from `init.cypher`):

| Relationship | From | To | Meaning |
|---|---|---|---|
| `HAS_KNOWN_REACTION` | Medication | Symptom | Known adverse reaction with `severity` + `meddra_term` |
| `CONTRAINDICATED_FOR` | Medication | Condition | Clinical contraindication with `reason` + `severity` |
| `INTERACTS_WITH` | Medication | Medication | Drug-drug interaction with `risk` + `severity` |

## Reference Enrichment Relationships

When reference data is available in the processor store, additional links are merged:

- `(Patient)-[:MANAGED_BY]->(Provider)` — with name, specialty, organization, npi
- `(Encounter)-[:SEEN_BY]->(Provider)` — linked from base event when both encounter_id and provider_id are present
- `(Patient)-[:REGISTERED_DEVICE]->(Device)`
- `(Patient)-[:KNOWN_MEDICATION]->(Medication)`
- `(Patient)-[:COVERED_BY]->(Payer)` — with plan_type, region, network_tier

Property enrichment examples:

- Patient: name, sex, age, risk_tier
- Provider: name, specialty, organization, npi
- Device: model, vendor, device_type, firmware_version, connectivity
- Medication: drug_class, safety_tier
- Payer: plan_type, region, network_tier

## How Graph Context Is Queried

`domains/healthcare/agents/domain/retrieval.py` `graph_search()` retrieves for selected patient IDs:

- conditions (with onset timestamps)
- symptoms
- observations (with lab_panel, specimen_type)
- medications (with drug_class, route, order_type)
- medication interactions
- vitals (with temperature, respiratory rate, alert)
- claims (via Procedure and Payer nodes)
- lab_signals (MAY_INDICATE edges from observations to conditions)
- icd10_codes (CODED_AS edges from conditions to ICD10Code nodes)
- adverse_events (REPORTED_ADVERSE_REACTION edges with medication and MedDRA term)
- contraindications (CONTRAINDICATED_FOR edges where the patient is currently on the medication)

Returned graph context is serialised into the LLM prompt by `_compact_graph_context()`, which surfaces lab signals, drug interactions, adverse events, contraindications, and device alerts.

## Pharmacovigilance Queries

### Adverse Events for a Patient

```cypher
MATCH (p:Patient {id: "patient-0001"})-[:REPORTED_ADVERSE_REACTION]->(ae:AdverseEvent)
MATCH (ae)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication)
RETURN p.id, ae.symptom_name, ae.severity, ae.meddra_term, m.name
ORDER BY ae.detected_ts DESC;
```

### Contraindication Violations (patient on a contraindicated drug)

```cypher
MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)<-[:CONTRAINDICATED_FOR]-(m:Medication)
WHERE EXISTS { MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m) }
RETURN p.id, m.name AS medication, c.name AS condition
ORDER BY p.id;
```

### Drugs with Most Adverse Events (signal ranking)

```cypher
MATCH (ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication)
RETURN m.name AS medication, count(ae) AS adverse_event_count,
       collect(DISTINCT ae.symptom_name)[..5] AS top_symptoms
ORDER BY adverse_event_count DESC
LIMIT 10;
```

### Multi-Drug Interaction Exposure

```cypher
MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m1:Medication)
MATCH (m1)-[i:INTERACTS_WITH]->(m2:Medication)
WHERE EXISTS { MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m2) }
RETURN p.id, m1.name, m2.name, i.risk, i.severity
ORDER BY i.severity DESC;
```

## Validation Queries

### Patient Journey

```cypher
MATCH (p:Patient {id: "patient-0001"})-[r]->(n)
RETURN p, r, n
LIMIT 100;
```

### Hyperkalemia Signal

```cypher
MATCH (p:Patient)-[:HAS_OBSERVATION]->(o:Observation)
WHERE o.name = "Potassium" AND o.value >= 5.5
RETURN p.id, o.name, o.value, o.unit, o.abnormal
ORDER BY o.value DESC;
```

### Medication Interaction Exposure

```cypher
MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m1:Medication)
MATCH (m1)-[i:INTERACTS_WITH]->(m2:Medication)
RETURN p.id, m1.name, m2.name, i.risk, i.severity;
```

### Coverage And Provider Context

```cypher
MATCH (p:Patient)-[:MANAGED_BY]->(pr:Provider)
OPTIONAL MATCH (p)-[:COVERED_BY]->(pay:Payer)
RETURN p.id, pr.name, pr.specialty, pay.name, pay.plan_type
LIMIT 50;
```

### Event Lineage

```cypher
MATCH (ce:ClinicalEvent)-[:ABOUT_PATIENT]->(p:Patient)
MATCH (ce)-[:FROM_SOURCE]->(src:SourceSystem)
RETURN ce.id, ce.event_type, p.id, src.name, ce.event_ts
ORDER BY ce.event_ts DESC
LIMIT 25;
```

## Operational Notes

- Merge patterns are idempotent by constrained identifiers.
- Reference enrichment is eventual with respect to transactional ordering.
- Replays can improve property completeness as more reference records arrive.
- This model is optimized for local explainability over full clinical normalization.

## Supply Chain Graph Model (parallel domain)

The supply-chain domain uses a separate Neo4j instance (`supplychain-neo4j` on port 7475/7688) with its own label set.

### Supply Chain Core Labels

| Label | Meaning |
| --- | --- |
| Supplier | Organization that provides parts or materials |
| Part | Component, raw material, or finished good |
| Facility | Factory, warehouse, distribution center, or port |
| Shipment | Tracked movement of goods between facilities |
| PurchaseOrder | Contractual order for parts from a supplier |
| QualityInspection | Inbound or in-process quality check result |
| DisruptionEvent | Supply chain disruption incident |
| RiskSignal | Computed risk indicator (single-source, geopolitical, quality) |
| SupplyChainEvent | Event lineage record |
| SourceSystem | Originating system (ERP, WMS, TMS, IoT) |

### Supply Chain Key Relationships

| Relationship | From | To | Properties |
| --- | --- | --- | --- |
| SUPPLIES | Supplier | Part | exclusive |
| DEPENDS_ON | Part | Part | bom_level |
| ORDERED_FROM | PurchaseOrder | Supplier | — |
| ORDERS_PART | PurchaseOrder | Part | — |
| SHIPPED_FROM | Shipment | Facility | — |
| SHIPPED_TO | Shipment | Facility | — |
| CONTAINS_PART | Shipment | Part | — |
| INSPECTED_PART | QualityInspection | Part | — |
| DISRUPTED_BY | Facility | DisruptionEvent | — |
| AFFECTS_PART | DisruptionEvent | Part | — |
| HAS_RISK_SIGNAL | Supplier/Part | RiskSignal | detected_ts |
| HOLDS_INVENTORY | Facility | Part | on_hand_qty, below_reorder, days_of_supply |

Constraints and seeds: `data-platform/supply-chain/neo4j/init.cypher` and `data-platform/supply-chain/neo4j/generated_ontology_seeds.cypher`.
