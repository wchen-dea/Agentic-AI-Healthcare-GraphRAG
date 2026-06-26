# Neo4j Healthcare Graph Model

## Overview

Neo4j stores the explicit healthcare relationship layer used by the GraphRAG API. The model is intentionally patient-centric: most traversals begin with one or more patients recovered from vector search and then expand to observations, conditions, symptoms, medication orders, device readings, claims, and reference entities.

## Core Labels

| Label | Purpose |
| --- | --- |
| `Patient` | canonical patient node |
| `Encounter` | encounter linkage when present |
| `ClinicalEvent` | raw event-level lineage node |
| `SourceSystem` | producing system such as Epic, LIS, or ClaimsSystem |
| `Condition` | diagnoses or inferred conditions |
| `Symptom` | symptoms extracted from notes |
| `Observation` | lab result observations |
| `Medication` | medication master and event-linked node |
| `MedicationOrder` | medication order event node |
| `Device` | device master node |
| `DeviceReading` | telemetry event node |
| `Claim` | claim event node |
| `Provider` | provider reference node |
| `Payer` | payer reference node |

## Constraints And Seed Data

The initialization script creates uniqueness constraints for:

- `Patient.id`
- `Encounter.id`
- `ClinicalEvent.id`
- `Observation.id`
- `MedicationOrder.id`
- `DeviceReading.id`
- `Claim.id`
- `Medication.name`
- `Condition.name`
- `Symptom.name`
- `SourceSystem.name`

Seed graph content also includes:

- `Warfarin` interacting with `Azithromycin` using `INTERACTS_WITH`
- a seeded `Hyperkalemia` condition node

## Base Relationship Model

| Pattern | Meaning |
| --- | --- |
| `(ClinicalEvent)-[:ABOUT_PATIENT]->(Patient)` | lineage from event to patient |
| `(ClinicalEvent)-[:FROM_SOURCE]->(SourceSystem)` | producing system lineage |
| `(ClinicalEvent)-[:DURING_ENCOUNTER]->(Encounter)` | encounter attachment when available |
| `(ClinicalEvent)-[:DOCUMENTS]->(domain entity)` | event documents a condition, symptom, observation, medication order, device reading, or claim |

## Patient-Centric Clinical Relationships

| Pattern | Created From |
| --- | --- |
| `(Patient)-[:HAS_CONDITION]->(Condition)` | clinical note diagnosis |
| `(Patient)-[:HAS_SYMPTOM]->(Symptom)` | clinical note symptom |
| `(Patient)-[:HAS_OBSERVATION]->(Observation)` | lab result |
| `(Patient)-[:HAS_MEDICATION_ORDER]->(MedicationOrder)` | medication order |
| `(MedicationOrder)-[:ORDERS_MEDICATION]->(Medication)` | medication order |
| `(Patient)-[:HAS_DEVICE_READING]->(DeviceReading)` | telemetry |
| `(DeviceReading)-[:MEASURED_BY]->(Device)` | telemetry |
| `(Patient)-[:HAS_CLAIM]->(Claim)` | claim event |

## Reference-Enrichment Relationships

These are added when matching reference data exists in the processor's in-memory store.

| Pattern | Enrichment Source |
| --- | --- |
| `(Patient)-[:MANAGED_BY]->(Provider)` | provider master data |
| `(Patient)-[:REGISTERED_DEVICE]->(Device)` | device master data |
| `(Patient)-[:KNOWN_MEDICATION]->(Medication)` | medication master data |
| `(Patient)-[:COVERED_BY]->(Payer)` | payer master data |

Reference enrichment also populates node properties such as:

- patient `name`, `sex`, `age`, `risk_tier`
- provider `name`, `specialty`, `organization`
- device `model`, `vendor`, `device_type`
- medication `drug_class`, `safety_tier`
- payer `plan_type`, `region`

## Derived Clinical Semantics

The graph currently includes a rule-based inference for potassium results:

| Rule | Graph Effect |
| --- | --- |
| lab name is `Potassium` and value >= 5.5 | `(Observation)-[:MAY_INDICATE {reason: "elevated_potassium"}]->(Condition {name: "Hyperkalemia"})` |

This makes the graph useful for relationship-based reasoning even though the ingestion pipeline remains lightweight.

## Write Patterns By Event Type

### Clinical Note

Creates or links:

- `Patient`
- `ClinicalEvent`
- `Condition`
- `Symptom`

### Lab Result

Creates or links:

- `Observation`
- optional `MAY_INDICATE` inference to `Hyperkalemia`

### Device Telemetry

Creates or links:

- `DeviceReading`
- `Device`

### Medication Order

Creates or links:

- `MedicationOrder`
- `Medication`

### Claim Status

Creates or links:

- `Claim`

## How The API Uses The Graph

The GraphRAG API does not execute arbitrary graph reasoning. It retrieves a focused patient summary containing:

- conditions,
- symptoms,
- observations,
- medications,
- medication interactions,
- recent vitals,
- claims.

This patient summary is then inserted into the LLM prompt alongside vector evidence from Qdrant.

## Validation Queries

### Patient Journey

```cypher
MATCH (p:Patient {id: "patient-0001"})-[r]->(n)
RETURN p, r, n
LIMIT 100;
```

### Abnormal Potassium

```cypher
MATCH (p:Patient)-[:HAS_OBSERVATION]->(o:Observation)
WHERE o.name = "Potassium" AND o.value >= 5.5
RETURN p.id, o.name, o.value, o.unit, o.abnormal
ORDER BY o.value DESC;
```

### Drug Interaction Risk

```cypher
MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m1:Medication)
MATCH (m1)-[i:INTERACTS_WITH]->(m2:Medication)
RETURN p.id, m1.name, m2.name, i.risk, i.severity;
```

### Provider Coverage View

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

## Modeling Notes

- `ClinicalEvent` preserves lineage and source traceability.
- Event-derived nodes such as `Observation` and `DeviceReading` use event IDs as stable unique identifiers.
- Reference-data nodes are gradually enriched over time rather than re-created per event.
- The model favors readability and local demos over exhaustive normalization.
