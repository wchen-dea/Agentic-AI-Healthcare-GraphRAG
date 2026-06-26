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
| Symptom | Symptom extracted from notes |
| Observation | Lab observation entity |
| Medication | Medication catalog node |
| MedicationOrder | Medication order event node |
| Device | Device catalog node |
| DeviceReading | Telemetry event node |
| Claim | Claims event node |
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

Seeded relationships include:

- (Warfarin)-[:INTERACTS_WITH {risk: bleeding_risk, severity: high}]->(Azithromycin)
- Condition node Hyperkalemia

## Base Lineage Pattern

Every transactional event writes the base lineage:

- (ClinicalEvent)-[:ABOUT_PATIENT]->(Patient)
- (ClinicalEvent)-[:FROM_SOURCE]->(SourceSystem)
- Optional (ClinicalEvent)-[:DURING_ENCOUNTER]->(Encounter)

This supports traceability from any downstream clinical assertion back to source event metadata.

## Event-Type Specific Patterns

### CLINICAL_NOTE

Creates/merges:

- Condition by diagnosis
- Symptom by symptom text

Relationships:

- (Patient)-[:HAS_CONDITION]->(Condition)
- (Patient)-[:HAS_SYMPTOM]->(Symptom)
- (ClinicalEvent)-[:DOCUMENTS]->(Condition)
- (ClinicalEvent)-[:DOCUMENTS]->(Symptom)

### LAB_RESULT

Creates/merges:

- Observation by event_id

Relationships:

- (Patient)-[:HAS_OBSERVATION]->(Observation)
- (ClinicalEvent)-[:DOCUMENTS]->(Observation)

Derived rule:

- If lab_name is Potassium and value >= 5.5:
  - (Observation)-[:MAY_INDICATE {reason: elevated_potassium}]->(Condition {name: Hyperkalemia})

### VITAL_SIGN

Creates/merges:

- DeviceReading by event_id
- Device by device_id

Relationships:

- (Patient)-[:HAS_DEVICE_READING]->(DeviceReading)
- (DeviceReading)-[:MEASURED_BY]->(Device)
- (ClinicalEvent)-[:DOCUMENTS]->(DeviceReading)

### MEDICATION_ORDER

Creates/merges:

- MedicationOrder by event_id
- Medication by medication name

Relationships:

- (MedicationOrder)-[:ORDERS_MEDICATION]->(Medication)
- (Patient)-[:HAS_MEDICATION_ORDER]->(MedicationOrder)
- (ClinicalEvent)-[:DOCUMENTS]->(MedicationOrder)

### CLAIM_STATUS

Creates/merges:

- Claim by claim_id

Relationships:

- (Patient)-[:HAS_CLAIM]->(Claim)
- (ClinicalEvent)-[:DOCUMENTS]->(Claim)

## Reference Enrichment Relationships

When reference data is available in the processor store, additional links are merged:

- (Patient)-[:MANAGED_BY]->(Provider)
- (Patient)-[:REGISTERED_DEVICE]->(Device)
- (Patient)-[:KNOWN_MEDICATION]->(Medication)
- (Patient)-[:COVERED_BY]->(Payer)

Property enrichment examples:

- Patient: name, sex, age, risk_tier
- Provider: name, specialty, organization
- Device: model, vendor, device_type
- Medication: drug_class, safety_tier
- Payer: plan_type, region

## How Graph Context Is Queried

rag-api/app.py graph_context() retrieves for selected patient IDs:

- conditions
- symptoms
- observations
- medications
- medication interactions
- vitals
- claims

Returned graph context is sent to the LLM prompt alongside vector evidence.

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
