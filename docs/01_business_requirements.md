# 01 — Business Requirements

This document explains **why** the platform exists and **what** it must do for the
people who use it. It does not describe implementation; for that see
[02 — Architecture](02_architecture.md) and [05 — AI Agents](05_ai_agents.md).

## 1. Purpose

Agentic AI Healthcare GraphRAG is a reference platform. It shows how streaming clinical
events, a knowledge graph and a vector index can be combined with governed AI agents to
answer clinical and operational questions with **cited, auditable evidence**.

The platform is **not**:

- a medical device, an electronic health record (EHR) or a clinical data repository (CDR);
- a source of clinical decisions — every answer is advisory and carries a safety caveat;
- connected to real patients — all data is synthetic.

A second domain, supply chain, reuses the same platform to prove that it is not
healthcare-specific. See [09 — Supply-Chain Domain](09_supply_chain_domain.md).

## 2. Problem statement

| Problem | Impact today | Platform response |
| --- | --- | --- |
| **Latency** | Clinical events land in batch warehouses hours later | Kafka + Flink update the graph and vector index within seconds |
| **Relationship blindness** | Keyword or vector search alone misses drug–drug, drug–condition and lab–condition links | A Neo4j knowledge graph holds explicit, ontology-governed relationships |
| **Retrieval–generation gap** | LLM answers are fluent but unsupported | Answers are synthesized only from retrieved vector and graph evidence, with grounding checks and citations |

## 3. Stakeholders

| Stakeholder | Primary need |
| --- | --- |
| Clinician (physician, nurse) | Fast patient summaries, medication and lab safety signals at the bedside |
| Clinical pharmacist | Interaction, contraindication and adverse-event review |
| Care manager | Cohort risk and follow-up prioritisation |
| Revenue-cycle / coding analyst | Coding gaps and claim-outcome risk |
| Biomedical / device team | Device alert triage |
| Compliance & privacy officer | Audit trail, role-based access, redaction |
| Platform / ML engineer | Observable, testable, portable runtime |
| Clinical informaticist / ontology owner | Governed vocabulary, rules and seed data |

## 4. Capabilities

### 4.1 Patient journey

Encounters, providers and diagnoses are linked as a graph, so the agent can explain a
patient's timeline: who saw them (`SEEN_BY`) and how they were coded (`CODED_AS`).

### 4.2 Drug safety

| Signal | Graph pattern | Example |
| --- | --- | --- |
| Drug–drug interaction | `(:Medication)-[:INTERACTS_WITH]->(:Medication)` | Warfarin + Aspirin; Clopidogrel + Omeprazole |
| Known adverse reaction | `(:Medication)-[:HAS_KNOWN_REACTION]->(:AdverseEvent)` (MedDRA terms) | Atorvastatin → Myalgia |
| Contraindication | `(:Medication)-[:CONTRAINDICATED_FOR]->(:Condition)` | Metformin – chronic kidney disease |
| Hospitalisation outcome | `-[:RESULTED_IN]->` FAERS outcome `HO` | Claims with CPT 99232, 99285, 99291 or 99223 |

Reference coverage in the seed ontology: **48 drugs, 41 interactions, 46 adverse
reactions, 23 contraindications**.

### 4.3 Lab interpretation

Fourteen threshold rules turn lab results into `MAY_INDICATE` edges to conditions, for
example:

| Lab | Rule | Indicates |
| --- | --- | --- |
| Potassium | ≥ 5.5 mmol/L | Hyperkalaemia |
| Troponin | > 0.04 ng/mL | Myocardial injury |
| HbA1c | ≥ 6.5 % | Diabetes |
| eGFR | < 60 mL/min | Chronic kidney disease |
| WBC | > 11 ×10⁹/L | Infection / inflammation |
| INR | > 3 | Over-anticoagulation |
| LDL | > 130 mg/dL | Hyperlipidaemia |

### 4.4 Revenue cycle

Claims are linked to procedures, diagnoses and payers so the agent can flag coding gaps
and claim-outcome risk.

### 4.5 Device alerts

Device telemetry is classified into tachycardia, hypoxia, hypertension and bradycardia
alerts and linked to the patient.

## 5. Use cases

| ID | Use case | Actor | Request type |
| --- | --- | --- | --- |
| UC-01 | Bedside decision support — "summarise this patient" | Clinician | `patient_summary` |
| UC-02 | Medication safety review | Pharmacist | `medication_safety` |
| UC-03 | Lab interpretation | Clinician | `lab_interpretation` |
| UC-04 | Adverse drug event detection | Pharmacist | `medication_safety` |
| UC-05 | Hospitalisation and claims risk | Care manager, revenue cycle | `coding_review` |
| UC-06 | Device alert triage | Device team, nurse | `patient_summary` |
| UC-07 | Coding audit | Coding analyst | `coding_review` |
| UC-08 | Cohort risk | Care manager | `cohort_triage` |

Request types are described in [05 — AI Agents](05_ai_agents.md#request-types).

## 6. Business rules

| ID | Rule |
| --- | --- |
| BR-01 | A lab result that crosses a rule threshold creates a `MAY_INDICATE` edge |
| BR-02 | A medication with a known reaction links to a MedDRA `AdverseEvent` |
| BR-03 | Co-prescribed interacting medications surface an `INTERACTS_WITH` signal |
| BR-04 | A medication contraindicated for an active condition surfaces a `CONTRAINDICATED_FOR` signal |
| BR-05 | Inpatient / emergency CPT codes set the FAERS hospitalisation (`HO`) flag |
| BR-06 | Evidence returned to the `generation` role is redacted |
| BR-07 | Every tool call writes an audit record |
| BR-08 | Responses never exceed the byte budget |
| BR-09 | Tools are gated by caller role (`X-Caller-Role`) |
| BR-10 | Raw event payloads are returned only to the `export` role |

## 7. Non-functional requirements

### 7.1 Guardrails

| Control | Default |
| --- | --- |
| Maximum response size | 50 000 bytes |
| Maximum answer length | 2 000 characters |
| Maximum question length | 1 000 characters |
| LLM timeout | 120 s (300 s in the local compose stack) |
| LLM temperature | 0.2 |
| Safety caveat | Appended to every answer |

### 7.2 Audit

Every tool call writes one JSON line to the audit log (`logs/agent_audit.log` by default):

| Field | Meaning |
| --- | --- |
| `timestamp` | UTC time of the call |
| `trace_id` | Correlates with MLflow traces and API responses |
| `tool_name` | Tool or endpoint invoked |
| `caller_id` | Caller role |
| `input_hash` | Hash of the input — raw input is never logged |
| `patient_scope` | Patient the call was scoped to, if any |
| `outcome` | `success`, `denied` or `error` |
| `latency_ms` | Duration |
| `response_size_bytes` | Size of the response |
| `error` | Error summary, if any |

### 7.3 Other qualities

- **Freshness** — events are visible to agents seconds after they are produced.
- **Explainability** — every answer lists its vector and graph evidence and a trace ID.
- **Human oversight** — low-confidence or high-risk answers can be paused for human
  review before release (healthcare).
- **Portability** — the same code runs on a laptop (Docker Compose), Minikube and EKS.

## 8. Constraints and assumptions

| Constraint | Implication |
| --- | --- |
| Synthetic data | No PHI; results are illustrative only |
| CPU-only local LLM | Local answers can take tens of seconds; production uses managed models |
| Embedding fidelity | The dev embedding model (MiniLM, 256-token window) trades recall for speed |
| Graph completeness | Signals are only as complete as the seed ontology and rules |
| Production boundary | The repository is a reference; production needs a real identity provider, secret manager and data agreements |
| No HL7 / FHIR | Events use a simplified Avro schema |
| Advisory only | Answers support, never replace, clinical judgement |

## 9. Business value

| Outcome | How the platform delivers it |
| --- | --- |
| Faster clinical insight | Seconds-fresh, pre-linked patient context |
| Fewer adverse drug events | Automatic interaction, contraindication and reaction checks |
| Better coding accuracy | Gap detection linked to claims and procedures |
| Trustworthy AI | Grounded answers, citations, guardrails and human review |
| Compliance readiness | Role-based tools, redaction and a complete audit trail |
| Reuse | Domain-neutral core proven by the supply-chain domain |

## Related

- [02 — Architecture](02_architecture.md)
- [10 — Healthcare Landscape and Roadmap](10_healthcare_landscape.md)
