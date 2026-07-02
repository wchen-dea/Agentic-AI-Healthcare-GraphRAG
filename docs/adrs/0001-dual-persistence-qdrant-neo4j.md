# ADR-0001: Use dual persistence (Qdrant + Neo4j)

- Status: accepted
- Date: 2026-06-26
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

Patient care data is highly heterogeneous and interconnected, spanning clinical records, laboratory results, medications, device telemetry, claims, and social determinants of health. As documented in the [Neo4j Medical Care industry guide](https://neo4j.com/developer/industry-use-cases/life-sciences/medical-care/), traditional relational databases struggle to capture these multi-dimensional relationships efficiently — queries frequently require numerous complex joins across tables, and the relational model cannot naturally express clinical causality (e.g. an observation _may indicate_ a condition, a medication _interacts with_ another medication).

Neo4j's labeled property graph model resolves this by representing clinical concepts as nodes, attributes as properties, and clinical events as typed, directional relationships that mirror real-world causality. This structure aligns naturally with the OMOP Common Data Model and enables integration of disparate source systems while preserving semantic richness.

However, graph traversal alone does not satisfy the system's retrieval requirements. Free-text clinical notes, unstructured observations, and cross-patient similarity queries require dense vector search that graph databases are not designed for. The GraphRAG pattern — retrieving vector-similar events and grounding them with explicit graph context — requires both capabilities simultaneously.

Specific pressures driving this decision:

1. **Patient journey complexity** — a single patient node connects conditions, symptoms, observations, medication orders, device readings, claims, providers, and payers; the graph naturally traverses this without joins.
2. **Drug safety signals** — `INTERACTS_WITH` and `MAY_INDICATE` relationships encode clinical rules that a vector store cannot express deterministically (e.g. Warfarin + Azithromycin bleeding risk).
3. **Multi-source event lineage** — every clinical event must be traceable back to its source system; a `ClinicalEvent → SourceSystem` edge is idiomatic in a graph, whereas it is an indexed foreign key in a relational schema and absent in a vector store.
4. **Semantic retrieval** — clinical notes and unstructured lab commentary are embedded and searched by meaning; graph traversal cannot substitute for ANN similarity search over 1 536-dimensional vectors.
5. **Real-time freshness** — Flink enriches and dual-writes to both sinks within the same pipeline execution; queries immediately combine fresh vector evidence with up-to-date graph context.

## Decision

Use **two stores with complementary, non-overlapping roles**:

| Store | Role | Query pattern |
|-------|------|---------------|
| **Neo4j** | Explicit relationship reasoning, patient journey traversal, drug safety signals, event lineage | Cypher graph traversal from `Patient` node |
| **Qdrant** | Semantic similarity retrieval over clinical embeddings | ANN search with payload filters |

### Neo4j graph model

The labeled property graph is **patient-centric**: every query begins at a `Patient` node and traverses outward. The core labels and their clinical meaning are:

| Label | Clinical meaning |
|-------|-----------------|
| `Patient` | Canonical patient identity |
| `Encounter` | Episode of care scope |
| `ClinicalEvent` | Source-event lineage record |
| `SourceSystem` | Origin system identity |
| `Condition` | Diagnosis / clinical condition |
| `Symptom` | Symptom extracted from notes |
| `Observation` | Lab result entity |
| `Medication` | Medication catalog node |
| `MedicationOrder` | Medication order event |
| `Device` | Device catalog node |
| `DeviceReading` | Device telemetry event |
| `Claim` | Claims event |
| `Provider` | Treating provider reference |
| `Payer` | Insurance payer reference |

Key relationship types encoding clinical causality:

- `(Patient)-[:HAS_CONDITION]->(Condition)`
- `(Patient)-[:HAS_OBSERVATION]->(Observation)`
- `(Patient)-[:HAS_MEDICATION_ORDER]->(MedicationOrder)-[:ORDERS_MEDICATION]->(Medication)`
- `(Observation)-[:MAY_INDICATE {reason}]->(Condition)` — derived signal (e.g. elevated potassium → Hyperkalemia)
- `(Medication)-[:INTERACTS_WITH {risk, severity}]->(Medication)` — drug safety edge
- `(ClinicalEvent)-[:ABOUT_PATIENT]->(Patient)` / `[:FROM_SOURCE]->(SourceSystem)` — lineage base pattern

### GraphRAG query integration

`rag-api` calls `graph_context(patient_ids)` to retrieve conditions, symptoms, observations, medications, interactions, vitals, and claims for the matched patients. This structured graph context is injected into the LLM prompt alongside the top-k Qdrant vector results, grounding the response in both semantic similarity and explicit clinical relationships.

### Flink dual-write strategy

The Flink enrichment job writes to both sinks in the same pipeline step:

1. Emit to **Qdrant** via gRPC `UpsertPoints` with content-hash deduplication.
2. Emit to **Neo4j** via Bolt with idempotent `MERGE` on all node uniqueness constraints.

Failure in either sink is handled independently; Neo4j write failures do not block Qdrant writes and vice versa. A Prometheus alert fires when either sink's error rate exceeds threshold.

## Consequences

Positive:

- Patient journey traversal is expressed as Cypher graph walks — no join complexity, natural extension as new event types are added.
- Drug safety and derived clinical signals (`MAY_INDICATE`, `INTERACTS_WITH`) are deterministic graph edges, not probabilistic similarity scores.
- Event lineage from every clinical assertion back to its source system is structurally guaranteed by the `ClinicalEvent` base pattern.
- Semantic retrieval across unstructured clinical text is handled by Qdrant without polluting the graph model.
- LLM responses are grounded in both fresh vector evidence and explicit relationship context, reducing hallucination on clinical facts.

Trade-offs:

- Two data systems increase operational surface: separate backup, monitoring, and upgrade paths required.
- Dual-write consistency is eventual; a window exists where Qdrant has a new embedding but Neo4j has not yet committed the corresponding graph edges.
- OMOP CDM alignment is structural (label/property conventions) but not formally validated; divergence can accumulate if new event types bypass the lineage base pattern.
- Graph query performance degrades on unbounded traversals; depth and result limits must be enforced in all Cypher queries.

## Alternatives Considered

- **Neo4j only with vector index** — Neo4j 5.x supports vector indexes, but ANN performance and payload filtering breadth do not match Qdrant for streaming upsert workloads at this scale.
- **Qdrant only with metadata payloads** — relationship traversal (multi-hop drug interaction chains, encounter-scoped event grouping) cannot be expressed as payload filters; graph structure would be lost.
- **Relational DB (PostgreSQL + pgvector)** — complex join paths for patient journey queries, no native relationship semantics; ruled out per the Neo4j medical care analysis of relational limitations.
- **Single document store (MongoDB)** — denormalised patient documents lose cross-patient relationship signals and require application-layer join logic.

## Rollout and Verification

1. **Constraint initialization** — `neo4j/init.cypher` creates uniqueness constraints for all core labels; idempotent on re-run.
2. **Seed reference data** — drug interaction edges (`INTERACTS_WITH`) and seeded condition nodes loaded at init time.
3. **Flink dual-sink smoke test** — produce a synthetic `CLINICAL_NOTE` event; verify `(Patient)-[:HAS_CONDITION]->` edge in Neo4j and matching embedding in Qdrant within 10 s.
4. **Drug safety signal test** — produce a synthetic `LAB_RESULT` with Potassium ≥ 5.5; verify `(Observation)-[:MAY_INDICATE]->(Condition {name: "Hyperkalemia"})` edge.
5. **GraphRAG end-to-end test** — query `rag-api` for a known patient; assert LLM response references both a retrieved document (Qdrant) and a graph-derived fact (Neo4j condition or interaction).
6. **Consistency monitoring** — Prometheus metric `neo4j_write_errors_total` and `qdrant_write_errors_total` with alerting on divergence rate > 1 %.

## Related

- [ADR-0002: Qdrant as the streaming vector store for real-time RAG](./0002-qdrant-streaming-vector-store.md)
- [Architecture](../ARCHITECTURE.md)
- [Neo4j Graph Model](../NEO4J_MODEL.md)
- [Neo4j — Medical Care Industry Use Cases](https://neo4j.com/developer/industry-use-cases/life-sciences/medical-care/)
