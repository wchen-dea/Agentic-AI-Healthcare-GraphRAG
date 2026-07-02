# Technical Specifications

## 1. Container Inventory

All services are defined in `docker-compose.yml`. The local stack runs entirely in Docker Compose; no external cloud services are required for development.

| Container | Image | Version | Host Ports | Role |
|-----------|-------|---------|-----------|------|
| `healthcare-zookeeper` | confluentinc/cp-zookeeper | 7.9.0 | 2181 | Kafka coordination |
| `healthcare-kafka` | confluentinc/cp-kafka | 7.9.0 | 9092, 29092 | Kafka broker 1 |
| `healthcare-kafka-2` | confluentinc/cp-kafka | 7.9.0 | 9093, 29093 | Kafka broker 2 |
| `healthcare-kafka-3` | confluentinc/cp-kafka | 7.9.0 | 9094, 29094 | Kafka broker 3 |
| `healthcare-schema-registry` | confluentinc/cp-schema-registry | 7.9.0 | 8081 | Avro schema registry |
| `healthcare-kafka-init` | confluentinc/cp-kafka | 7.9.0 | — | One-shot topic provisioning |
| `healthcare-conduktor-postgres` | postgres | 14 | — | Conduktor metadata store |
| `healthcare-conduktor-console` | conduktor/conduktor-console | latest | 8085 | Kafka management UI |
| `healthcare-qdrant` | qdrant/qdrant | latest | 6333 (HTTP), 6334 (gRPC) | Vector store |
| `healthcare-neo4j` | neo4j | 5.26.2 | 7474 (HTTP), 7687 (Bolt) | Graph database |
| `healthcare-neo4j-init` | neo4j | 5.26.2 | — | One-shot Cypher seed |
| `healthcare-neodash` | neo4jlabs/neodash | latest | 5005 | Neo4j dashboard UI |
| `healthcare-ollama` | ollama/ollama | latest | 11434 | Local LLM inference |
| `healthcare-flink-jobmanager` | custom (flink-app/Dockerfile) | — | 8082 | Flink JobManager |
| `healthcare-flink-taskmanager` | custom (flink-app/Dockerfile) | — | — | Flink TaskManager |
| `healthcare-flink-app` | custom (flink-app/Dockerfile) | — | — | PyFlink job submitter |
| `healthcare-event-producer` | custom (producer/Dockerfile) | — | — | Synthetic event generator |
| `healthcare-rag-api` | custom (rag-api/Dockerfile) | — | 8000 | GraphRAG REST + MCP API |
| `healthcare-provider-web` | custom (webapp/Dockerfile) | — | 8088 | Provider web UI (Nginx) |
| `healthcare-prometheus` | prom/prometheus | latest | 9090 | Metrics scraper |
| `healthcare-blackbox-exporter` | prom/blackbox-exporter | latest | 9115 | HTTP probe exporter |
| `healthcare-grafana` | grafana/grafana | latest | 3000 | Metrics dashboards |
| `localstack` | localstack/localstack | 3.8.0 | 4566, 4510–4559 | Local AWS-compatible services |

---

## 2. Library Versions

### rag-api (`rag-api/requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | 0.115.0 | REST API framework |
| uvicorn | 0.31.1 | ASGI server |
| qdrant-client | 1.11.3 | Qdrant gRPC/HTTP client |
| neo4j | 5.24.0 | Neo4j Bolt driver |
| requests | 2.32.3 | HTTP client for Ollama |
| pydantic | ≥2.11.7,<3.0.0 | Request/response validation |
| mcp | 1.28.0 | FastMCP embedded server |
| httpx | 0.27.2 | Async HTTP (MCP transport) |
| email-validator | ≥2.2.0 | Pydantic email field support |
| prometheus-client | 0.23.1 | Metrics exposition |

> **Note:** `pydantic` is pinned with a range (`>=2.11.7,<3.0.0`) rather than an exact version because `mcp==1.28.0` requires `pydantic>=2.12.0` on Python 3.14. The range allows pip to resolve on Python 3.11 (CI/Docker target) and 3.14+ without conflict.

### flink-app (`flink-app/requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| apache-flink | 1.20.1 | PyFlink DataStream API |
| confluent-kafka | 2.5.3 | Kafka consumer (Avro) |
| fastavro | 1.9.7 | Avro deserialization |
| neo4j | 5.24.0 | Neo4j Bolt driver |
| qdrant-client | 1.11.3 | Qdrant upsert client |
| requests | 2.32.3 | HTTP utilities |

### producer (`producer/requirements.txt`)

| Package | Version | Purpose |
|---------|---------|---------|
| confluent-kafka | 2.6.1 | Kafka Avro producer |
| faker | 25.8.0 | Synthetic data generation |
| requests | 2.32.3 | Schema Registry registration |
| fastavro | 1.9.5 | Avro serialization |

### Python runtime

| Component | Python version | Base image |
|-----------|---------------|-----------|
| rag-api | 3.11 | python:3.11-slim |
| flink-app | 3.11 (via Flink image) | custom Flink Dockerfile |
| producer | 3.11 | python:3.11-slim |
| mcp-server (standalone) | 3.11 | python:3.11-slim |
| CI test runner | 3.11 | ubuntu-latest + setup-python@v5 |

---

## 3. Kafka Configuration

### Cluster topology

| Property | Value |
|----------|-------|
| Brokers | 3 (IDs 1, 2, 3) |
| Replication factor (default) | 3 |
| Min in-sync replicas | 2 |
| Default partitions | 3 |
| Auto-create topics | Disabled |
| Offsets topic replication | 3 |
| Transaction state log replication | 3 |
| Transaction state log min ISR | 2 |
| Coordination | ZooKeeper 2181 |
| Inter-broker listener | PLAINTEXT (internal) |

### Listener map

| Listener name | Binding | Accessible from |
|--------------|---------|----------------|
| PLAINTEXT | `kafka:29092`, `kafka2:29093`, `kafka3:29094` | Containers (internal) |
| PLAINTEXT_HOST | `0.0.0.0:9092/9093/9094` | Host machine |

### Topic topology

| Topic | Partitions | Replication | Event type | Producer fn |
|-------|-----------|-------------|-----------|------------|
| `healthcare.ehr.events` | 3 | 3 | `CLINICAL_NOTE` | `ehr_event` |
| `healthcare.lab.results` | 3 | 3 | `LAB_RESULT` | `lab_event` |
| `healthcare.device.telemetry` | 3 | 3 | `VITAL_SIGN` | `device_event` |
| `healthcare.pharmacy.orders` | 3 | 3 | `MEDICATION_ORDER` | `pharmacy_event` |
| `healthcare.claims.events` | 3 | 3 | `CLAIM_STATUS` | `claims_event` |
| `healthcare.master.patients` | 1 | 3 | `PATIENT_MASTER_UPSERT` | `patient_reference_event` |
| `healthcare.master.providers` | 1 | 3 | `PROVIDER_MASTER_UPSERT` | `provider_reference_event` |
| `healthcare.master.devices` | 1 | 3 | `DEVICE_MASTER_UPSERT` | `device_reference_event` |
| `healthcare.master.medications` | 1 | 3 | `MEDICATION_MASTER_UPSERT` | `medication_reference_event` |
| `healthcare.master.payers` | 1 | 3 | `PAYER_MASTER_UPSERT` | `payer_reference_event` |
| `healthcare.dlq.events` | 1 | 3 | — | Reserved (not written) |

### Wire format

- **Key:** UTF-8 bytes of `patient_id` when present, otherwise `event_id`
- **Value:** Confluent Avro binary (magic byte 0x00 + 4-byte schema ID + Avro payload)
- **Schema subject naming:** `{topic}-value`

---

## 4. Avro Envelope Schema

**File:** `schemas/medical_event.avsc`  
**Namespace:** `com.healthcare.graphrag`  
**Record name:** `MedicalEvent`  
**Schema version:** `1.0.0`

| Field | Avro type | Default | Notes |
|-------|-----------|---------|-------|
| `event_id` | `string` | — | UUID v4 |
| `event_ts` | `string` | — | ISO-8601 UTC |
| `source_system` | `string` | — | EHR system name or source identifier |
| `source_type` | `string` | — | `EHR`, `LAB`, `DEVICE`, `PHARMACY`, `CLAIMS`, `REFERENCE` |
| `event_type` | `string` | — | `CLINICAL_NOTE`, `LAB_RESULT`, `VITAL_SIGN`, `MEDICATION_ORDER`, `CLAIM_STATUS`, `*_MASTER_UPSERT` |
| `patient_id` | `["null","string"]` | `null` | Absent for non-patient reference events |
| `encounter_id` | `["null","string"]` | `null` | Optional encounter scope |
| `provider_id` | `["null","string"]` | `null` | Optional attending provider |
| `payload_json` | `string` | — | Event-type-specific JSON object (see kafka_schema.md) |
| `schema_version` | `string` | `"1.0.0"` | Envelope schema version |

---

## 5. Flink Configuration

### Job parameters

| Property | Value | Source |
|----------|-------|--------|
| Default parallelism | 2 | `FLINK_PROPERTIES` |
| Task slots per TaskManager | 4 | `FLINK_PROPERTIES` |
| State backend | `hashmap` | `FLINK_PROPERTIES` |
| Checkpointing interval | 10 000 ms | `FLINK_PROPERTIES` / `FLINK_CHECKPOINT_INTERVAL_MS` |
| Checkpointing mode | `EXACTLY_ONCE` | `FLINK_PROPERTIES` |
| Python executable | `/usr/bin/python3` | `FLINK_PROPERTIES` |
| Job parallelism (runtime) | 1 | `FLINK_JOB_PARALLELISM` env var |
| Kafka consumer group | `healthcare-graphrag-pyflink` | `FLINK_KAFKA_GROUP_ID` env var |

### Kafka consumer behaviour

- One `KafkaSource` per topic; group ID suffix: `{FLINK_KAFKA_GROUP_ID}-{topic-name}`
- Start offset: earliest (replay-friendly)
- Topics consumed: all 10 transactional + reference topics
- Reference events update an in-process reference store; transactional events trigger
  dual-sink writes to Qdrant and Neo4j

### Embedding

| Property | Value |
|----------|-------|
| Algorithm | Stable MD5 bag-of-words |
| Dimensions | 384 |
| Normalisation | L2 (unit vector) |
| Token extraction | Lowercase whitespace split |

> The stable embedding is a deterministic, dependency-free surrogate. Replace with a neural
> model (e.g. `sentence-transformers/all-MiniLM-L6-v2`) for production semantic quality.

---

## 6. Qdrant Collection Specification

| Property | Value |
|----------|-------|
| Collection name | `healthcare_events` (default; env `QDRANT_COLLECTION`) |
| Vector size | 384 |
| Distance metric | Cosine |
| HTTP port | 6333 |
| gRPC port | 6334 |
| Upsert API | gRPC `UpsertPoints` |

### Point payload fields

| Field | Type | Indexed | Description |
|-------|------|---------|-------------|
| `event_id` | string | — | Source event UUID |
| `event_ts` | string | — | ISO-8601 event timestamp |
| `event_type` | string | ✓ (filter) | `CLINICAL_NOTE`, `LAB_RESULT`, etc. |
| `patient_id` | string | ✓ (filter) | Used for patient-scoped ANN queries |
| `source_system` | string | — | Originating system |
| `source_type` | string | — | `EHR`, `LAB`, etc. |
| `enriched` | bool | — | Whether reference data was injected |
| `reference_hit_count` | int | — | Number of matched reference entities |
| `text` | string | — | Rendered clinical text (embedded) |
| `payload` | object | — | Full enriched domain payload |

---

## 7. Neo4j Graph Specification

| Property | Value |
|----------|-------|
| Image version | neo4j:5.26.2 |
| Plugin | APOC |
| HTTP port | 7474 |
| Bolt port | 7687 |
| Auth | `neo4j / ${NEO4J_PASSWORD:-healthcare123}` |
| Init script | `neo4j/init.cypher` (mounted at startup) |

### Node labels (19)

| Label | Unique constraint | Key property |
|-------|-----------------|--------------|
| `Patient` | ✓ | `id` |
| `Encounter` | ✓ | `id` |
| `ClinicalEvent` | ✓ | `id` |
| `SourceSystem` | ✓ | `name` |
| `Condition` | ✓ | `name` |
| `ICD10Code` | ✓ | `code` |
| `Symptom` | ✓ | `name` |
| `Observation` | ✓ | `id` |
| `Medication` | ✓ | `name` (+ `activeIngredient`, `isValidatedTradeNameUsed`) |
| `MedicationOrder` | ✓ | `id` |
| `Device` | ✓ | `id` |
| `DeviceReading` | ✓ | `id` |
| `Claim` | ✓ | `id` |
| `Procedure` | ✓ | `code` |
| `Provider` | ✓ | `id` (+ `npi`) |
| `Payer` | ✓ | `name` |
| `AdverseEvent` | ✓ | `id` |
| `AdverseOutcome` | ✓ | `code` (DE / LT / HO / DS / CA / OT) |

### Key relationship types

| Relationship | From → To | Properties |
|-------------|----------|-----------|
| `HAS_CONDITION` | Patient → Condition | `onset_ts` |
| `HAS_OBSERVATION` | Patient → Observation | — |
| `HAS_MEDICATION_ORDER` | Patient → MedicationOrder | — |
| `HAS_DEVICE_READING` | Patient → DeviceReading | — |
| `HAS_CLAIM` | Patient → Claim | — |
| `HAS_SYMPTOM` | Patient → Symptom | — |
| `MAY_INDICATE` | Observation → Condition | `reason` |
| `CODED_AS` | Condition → ICD10Code | — |
| `ORDERS_MEDICATION` | MedicationOrder → Medication | — |
| `INTERACTS_WITH` | Medication → Medication | `risk`, `severity`, `mechanism` |
| `HAS_KNOWN_REACTION` | Medication → Symptom | `severity`, `meddra_term` |
| `CONTRAINDICATED_FOR` | Medication → Condition | `reason`, `severity` |
| `REPORTED_ADVERSE_REACTION` | Patient → AdverseEvent | — |
| `ASSOCIATED_WITH_MEDICATION` | AdverseEvent → Medication | — |
| `TRIGGERED_BY_EVENT` | AdverseEvent → ClinicalEvent | — |
| `FOR_PROCEDURE` | Claim → Procedure | — |
| `SUBMITTED_TO` | Claim → Payer | — |
| `RESULTED_IN` | Claim → AdverseOutcome | — |
| `SEEN_BY` | Encounter → Provider | — |
| `MANAGED_BY` | Patient → Provider | — |
| `COVERED_BY` | Patient → Payer | — |

### Seed data (from `neo4j/init.cypher`)

| Category | Count |
|----------|-------|
| Uniqueness constraints | 19 |
| Drug-drug `INTERACTS_WITH` pairs (with mechanism) | 15 |
| `AdverseOutcome` nodes | 6 |
| `HAS_KNOWN_REACTION` edges | ≥ 20 |
| `CONTRAINDICATED_FOR` edges | 11 |
| Seeded `Condition` nodes | 20 |
| Medications with `activeIngredient` | 24 |

---

## 8. RAG API Specification

**Base URL (local):** `http://localhost:8000`  
**Framework:** FastAPI 0.115.0  
**Python:** 3.11

### REST endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Liveness probe |
| `GET` | `/metrics` | None | Prometheus metrics (text/plain) |
| `POST` | `/query` | `X-Caller-Role` header | Full GraphRAG query (vector + graph + LLM) |
| `GET` | `/mcp/health` | None | MCP diagnostic probe |
| `*` | `/mcp` | MCP protocol | FastMCP Streamable HTTP endpoint |

### MCP tools (5)

| Tool | Caller role | Backing path |
|------|------------|-------------|
| `patient_context_get` | `read_only` | graph_context() |
| `vector_evidence_search` | `read_only` | vector_context() |
| `graphrag_answer_generate` | `generation` | run_query() + ask_ollama() |
| `risk_summary_generate` | `generation` | run_query() + prompt template |
| `evidence_bundle_export` | `export` | run_query() + bounded text |

### Role-based access policy (`rag-api/config/tool_policies.json`)

| Role | Permitted tools |
|------|----------------|
| `read_only` | `patient_context_get`, `vector_evidence_search` |
| `generation` | `query`, `graphrag_answer_generate`, `risk_summary_generate` |
| `export` | `evidence_bundle_export` |

### Configurable limits (environment variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_API_MAX_QUESTION_CHARS` | 1000 | Max question length |
| `RAG_API_MAX_CONTEXT_ITEMS` | 5 | Max items from each retrieval path |
| `RAG_API_MAX_EVIDENCE_CHARS` | 240 | Max chars per vector evidence text (export role) |
| `RAG_API_MAX_ANSWER_CHARS` | 2000 | Max chars in LLM answer before truncation |
| `RAG_API_MAX_RESPONSE_BYTES` | 50 000 | Hard byte budget for entire response payload |
| `LLM_TIMEOUT_SECONDS` | 120 | Ollama request timeout |
| `LLM_MAX_TOKENS` | 1200 | Ollama `num_predict` |
| `OLLAMA_MODEL` | `llama3.1` | Model pulled and used for generation |

### Response shape (`/query`)

```json
{
  "question": "...",
  "patients": ["patient-0001"],
  "vector_context": [{"score": 0.91, "event_id": "...", "event_type": "LAB_RESULT", "text_redacted": true}],
  "graph_context": [{
    "patient_id": "patient-0001",
    "conditions": [], "symptoms": [], "observations": [],
    "medications": [], "interactions": [], "vitals": [],
    "claims": [], "lab_signals": [], "icd10_codes": [],
    "adverse_events": [], "contraindications": []
  }],
  "answer": "...",
  "retrieved_at": "2026-07-02T...",
  "trace_id": "uuid",
  "guardrails": {
    "evidence_text_redacted": true,
    "evidence_access_level": "none",
    "graph_access_level": "standard",
    "max_context_items": 5,
    "max_response_bytes": 50000,
    "response_truncated": false
  }
}
```

---

## 9. Producer Specification

| Property | Value |
|----------|-------|
| Event interval | 1 s (default; `EVENT_INTERVAL_SECONDS`) |
| Patient pool | 100 (`patient-0001` … `patient-0100`) |
| Provider pool | 20 (`provider-001` … `provider-020`) |
| Transactional event share | 80 % |
| Reference event share | 20 % |
| Schema registration | On startup, retries until Schema Registry is healthy |
| Serialization | Confluent AvroSerializer (`to_dict` identity) |

### Event type volumes

| Event type | Generator function | Medications/labs/etc. covered |
|-----------|-------------------|-------------------------------|
| `CLINICAL_NOTE` | `ehr_event` | 24 diagnoses, 20 symptoms, 6 EHR systems, 6 note templates, ICD-10 code |
| `LAB_RESULT` | `lab_event` | 18 lab tests with per-test abnormality threshold, lab panel, specimen type |
| `VITAL_SIGN` | `device_event` | 5 device sources, device types, temp, RR, glucose, alert |
| `MEDICATION_ORDER` | `pharmacy_event` | 24 medications with drug class, 9 frequencies, 6 routes, order type, days supply |
| `CLAIM_STATUS` | `claims_event` | 10 payers, 19 CPT codes with descriptions, ICD-10 diagnosis code, billed/allowed amounts |

---

## 10. Observability Endpoints

| Service | URL | What it exposes |
|---------|-----|----------------|
| Prometheus | `http://localhost:9090` | Metric TSDB and query UI |
| Grafana | `http://localhost:3000` | Dashboards (admin/admin123) |
| Flink UI | `http://localhost:8082` | Job state, task slots, checkpoints |
| Blackbox Exporter | `http://localhost:9115` | HTTP probe results |
| Conduktor Console | `http://localhost:8085` | Kafka topic browser (admin@healthcare.local / Admin@123!) |
| Neo4j Browser | `http://localhost:7474` | Cypher query UI (neo4j / healthcare123) |
| NeoDash | `http://localhost:5005` | Pre-built graph dashboards |
| RAG API metrics | `http://localhost:8000/metrics` | Prometheus text format |

### Key Prometheus metrics

| Metric | Type | Labels |
|--------|------|--------|
| `rag_api_http_request_duration_seconds` | Histogram | `method`, `path`, `status` |
| `rag_api_tool_execution_duration_seconds` | Histogram | `tool`, `outcome` |
| `rag_api_tool_execution_total` | Counter | `tool`, `outcome` |

---

## 11. CI / CD Pipeline

**File:** `.github/workflows/rag-api-contracts.yml`  
**Trigger:** push or PR to `dev` branch touching `rag-api/**` or the workflow file itself

| Job | Runner | Steps |
|-----|--------|-------|
| `contract-tests` | ubuntu-latest | Checkout → Python 3.11 + pip cache → install `rag-api/requirements.txt` → `python rag-api/tests/test_contracts.py` (6 tests, ~1 s) |
| `container-build` | ubuntu-latest | Checkout → `docker build -f rag-api/Dockerfile` |

Both jobs run in parallel. Neither requires live external services (all dependencies mocked in contract tests).

**File:** `.github/workflows/deploy-ai-prd.yml`  
Separate production deployment workflow targeting the AI services bundle under `deploy/production/`.

---

## 12. Key Environment Variables

Variables read from `.env` (gitignored) or compose `environment` blocks. All have safe development defaults.

| Variable | Default | Component | Description |
|----------|---------|-----------|-------------|
| `NEO4J_PASSWORD` | `healthcare123` | neo4j, flink-app, rag-api | Neo4j auth password |
| `NEO4J_URI` | `bolt://neo4j:7687` | flink-app, rag-api | Neo4j Bolt URI |
| `NEO4J_USER` | `neo4j` | all Neo4j clients | Neo4j username |
| `QDRANT_URL` | `http://qdrant:6333` | flink-app, rag-api | Qdrant HTTP base URL |
| `QDRANT_COLLECTION` | `healthcare_events` | flink-app, rag-api | Collection name |
| `OLLAMA_URL` | `http://ollama:11434` | rag-api | Ollama inference endpoint |
| `OLLAMA_MODEL` | `llama3.1` | rag-api | Model name for generation |
| `KAFKA_BOOTSTRAP_SERVERS` | `kafka:29092,...` | producer, flink-app | Broker list |
| `SCHEMA_REGISTRY_URL` | `http://schema-registry:8081` | producer, flink-app | Schema Registry URL |
| `EVENT_INTERVAL_SECONDS` | `1` | producer | Seconds between emitted events |
| `CONDUKTOR_POSTGRES_PASSWORD` | `change_me` | conduktor-postgres | Postgres password |
| `CONDUKTOR_ADMIN_PASSWORD` | `Admin@123!` | conduktor-console | Console admin password |
| `GRAFANA_ADMIN_PASSWORD` | `admin123` | grafana | Grafana admin password |
| `FLINK_KAFKA_GROUP_ID` | `healthcare-graphrag-pyflink` | flink-app | Kafka consumer group prefix |
| `FLINK_JOB_PARALLELISM` | `1` | flink-app | PyFlink job parallelism |
| `FLINK_CHECKPOINT_INTERVAL_MS` | `10000` | flink-app | Checkpoint interval |
| `RAG_API_DEFAULT_CALLER_ROLE` | `generation` | rag-api | Role when no header present |
| `RAG_API_AUDIT_LOG_PATH` | `logs/rag_api_audit.log` | rag-api | Audit JSONL output path |
