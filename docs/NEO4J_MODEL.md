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

Initialization in neo4j/init.cypher creates uniqueness constraints for:

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
Drug safety seed data (FAERS-aligned):

- 6 `AdverseOutcome` nodes: DE, LT, HO, DS, CA, OT
- `HAS_KNOWN_REACTION` edges: 10 medications → matching symptom strings (e.g. Lisinopril→cough, Atorvastatin→leg cramps, Metoprolol→dizziness)
- `CONTRAINDICATED_FOR` edges: 6 medication-condition pairs (e.g. Metformin→CKD, Lisinopril→Hyperkalemia, Vancomycin→CKD)
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

rag-api/app.py `graph_context()` retrieves for selected patient IDs:

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
