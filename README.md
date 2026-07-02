# Agentic AI Healthcare GraphRAG

A healthcare-focused hybrid GraphRAG system built on Kafka, PyFlink, Qdrant, Neo4j, FastAPI, and Ollama.

## Summary

This project provides a healthcare AI platform blueprint across three dimensions:

- Technical leadership: streaming-first ingestion, dual evidence stores (vector plus graph), and agent-ready APIs (REST + MCP) on shared reasoning logic.
- Industry innovation: one reusable architecture for clinical, operational, and financial healthcare AI workflows.
- Implementation maturity: complete local development stack plus production-ready deployment configuration variants for AI deliverables.

Repository intent:

- Root-level Docker Compose, default credentials, and local env examples are for development and synthetic-demo use only.
- Production readiness in this repository refers to the deployment configuration assets under `deploy/production/`, not to the root local stack defaults.

Production boundary in this repository:

- In scope: rag-api (embedded MCP), provider-web, optional standalone mcp-server, separate monitoring config.
- Out of scope: source data systems, Confluent Kafka platform, and Apache Flink platform (independently managed).

## Tech Stack

- Streaming: Apache Kafka, Confluent Schema Registry, Apache Flink (PyFlink)
- Data Stores: Qdrant (vector), Neo4j (graph)
- API and AI: FastAPI + embedded FastMCP, Ollama (local-first)
- Frontend: Static provider web app (Nginx-served)
- Observability: Prometheus, Grafana, Blackbox Exporter
- Operations and Tooling: Docker Compose, Conduktor, NeoDash

## What This Repository Runs

End-to-end healthcare intelligence pipeline:

- generates synthetic transactional and reference healthcare events,
- streams events through Kafka and Schema Registry,
- processes streams in a native PyFlink DataStream job,
- enriches transactional events with master data,
- writes dual sinks to Qdrant and Neo4j,
- serves GraphRAG responses through a FastAPI API backed by Ollama,
- exposes provider and observability surfaces for local exploration.

## Healthcare Domain Readiness

The platform is reusable by design: core platform layers stay stable while domain behavior is added through topic contracts, enrichment rules, graph models, and prompt policy.

| Healthcare Section | Example Data Sources | Typical Outcomes |
| --- | --- | --- |
| Clinical Operations | EHR notes, labs, telemetry | Earlier risk detection, clinician-ready summaries |
| Revenue Cycle | Claims, coding events, prior-auth records | Denial reduction, coding consistency insights |
| Payer and Utilization | Claims timelines, authorization decisions | Utilization trend detection, anomaly triage |
| Population Health | Longitudinal encounters, chronic-condition signals | Cohort risk stratification, outreach prioritization |
| Medication Safety | Orders, interaction knowledge base, FAERS adverse event reporting | Real-time adverse event detection, contraindication alerts, drug-drug interaction mechanism tracing, pharmacovigilance signal ranking |
| Device and Remote Monitoring | Device telemetry, alerts, maintenance events | Faster anomaly response, operational efficiency |

## Innovation Highlights

- Real-time healthcare intelligence stack: Kafka + Flink processing with Avro schema-governed event contracts.
- Hybrid GraphRAG retrieval: Qdrant vector evidence plus Neo4j relationship context in one grounded answer flow.
- Streaming enrichment pattern: reference/master data fused into transactional events before vector and graph persistence.
- Local-first AI runtime with bounded generation controls and model fallback for resilient development workflows.
- Explainability by design: API returns both vector_context and graph_context alongside generated responses.
- Operations-first engineering: Prometheus, Grafana, Flink UI, and Conduktor integrated for full-stack observability.

## Runtime Summary

```text
Producer
  -> Kafka topics
  -> Native PyFlink DataStream job (HealthcareGraphRagPyFlinkJob)
     -> reference-store enrichment
     -> Qdrant vector upserts
     -> Neo4j graph merges
  -> FastAPI GraphRAG API
     -> Qdrant semantic context
     -> Neo4j relationship context
     -> Ollama answer generation

Ops/UI
  -> Provider web app
  -> Flink dashboard
  -> Conduktor Console
  -> Prometheus + Grafana + Blackbox Exporter
  -> Neo4j Browser + NeoDash
```

## LLM Strategy

- Local default: Ollama using OLLAMA_URL and OLLAMA_MODEL.
- Current implementation in `rag-api/app.py` uses Ollama `/api/generate` directly.
- Active latency and output controls: LLM_TIMEOUT_SECONDS and LLM_MAX_TOKENS.
- Temperature is currently fixed in code (`0.2`) and is not yet env-configurable.
- Anthropic/OpenAI provider routing remains a documented extension path, not the active local runtime.

### Ollama Cost Model (Local)

- Local Ollama inference has no per-token or per-request API fee.
- Local operating costs still exist (hardware, power, and maintenance time).
- If you move Ollama to cloud VMs, cloud compute/storage/network costs apply.
- If you switch to managed providers (Anthropic/OpenAI), provider token pricing applies.

## Key Capabilities

- Hybrid retrieval that combines semantic nearest-neighbor evidence from Qdrant with patient-centric relationship context from Neo4j.
- Reference-data enrichment for patients, providers, devices, medications, and payers before sink writes.
- 14-rule lab signal engine: each lab result is evaluated against clinical thresholds at ingest time and `MAY_INDICATE` edges are written atomically to Neo4j (Hyperkalemia, AMI, CKD, Anemia, Hyperlipidemia, Hypothyroidism, and more).
- FAERS-aligned pharmacovigilance: adverse event detection fires after every `CLINICAL_NOTE` event by matching the documented symptom against `HAS_KNOWN_REACTION` graph edges for the patient's currently ordered medications.
- Drug safety knowledge graph: `INTERACTS_WITH` edges carry mechanism annotations; `HAS_KNOWN_REACTION` edges carry MedDRA terms and severity; `CONTRAINDICATED_FOR` edges encode clinical contraindication reasoning — all seeded at stack startup from `neo4j/init.cypher`.
- ICD-10 coding: clinical note events carry an `icd10_code` field written as `(Condition)-[:CODED_AS]->(ICD10Code)` edges, enabling coding-gap queries across the graph.
- Expanded synthetic event scope: 24-medication catalog with active ingredients, 18-lab-test panels with per-test abnormality thresholds, device alerts (tachycardia, hypoxia, hypertension), CPT procedure descriptions, and claims financial fields (billed/allowed amounts, service dates).
- graph_context response includes `lab_signals`, `adverse_events`, `contraindications`, `icd10_codes`, and enriched `medications` / `vitals` / `claims` payloads visible in every API and MCP tool response.
- Native Flink job visibility from the Flink dashboard.
- Local observability for Kafka, Flink, Neo4j, and Qdrant.
- Provider-facing UI for query workflows without curl.
- Embedded MCP tool endpoint in rag-api for agent integration without a separate MCP service.
- Role-based API and MCP guardrails with caller-policy authorization, evidence redaction rules, and response budget metadata.
- CI-backed rag-api contract checks plus container build validation for the hardened API surface.

## MCP Quick Verify

```bash
curl -s http://localhost:8000/mcp/health | jq .
python3 ./scripts/mcp_smoke_test.py
```

## Quick Start

This quick start is for local development only. It is not a production deployment path.

Prerequisites:

- Docker Desktop or Docker Engine with Compose support
- jq (recommended for shell validations)
- Enough disk for Ollama model download (roughly 5 GB+)

Start the full stack:

```bash
cd /path/to/Agentic-AI-Healthcare-GraphRAG
cp .env.example .env
docker compose up -d --build
```

The local stack follows the same externalized configuration pattern as the production bundle: copy `.env.example` to `.env` and keep local credentials and secret-like values in `.env`, not hardcoded in source-controlled Compose overrides.

Startup ordering in the local stack is intentionally gated:

- Schema Registry must report healthy before topic initialization runs.
- Topic initialization must complete before the producer starts.
- The producer also waits and retries until Schema Registry is reachable before schema registration.

### Local Secret Configuration

For local development, configure secret-like values in `.env` only.

1. Create a local env file:

```bash
cp .env.example .env
```

1. Edit `.env` and set the local values you want to use, especially:

- `NEO4J_PASSWORD`
- `CONDUKTOR_POSTGRES_PASSWORD`
- `CONDUKTOR_ADMIN_PASSWORD`
- `GRAFANA_ADMIN_PASSWORD`

1. Keep `.env` local only. It is ignored by git and should not be committed.

1. Recreate or restart affected services after changing secret-bearing values:

```bash
docker compose up -d --build
```

The values in `.env.example` are development placeholders. Replace them in `.env` if you want non-default local credentials.

Local Kafka topology after startup:

- broker 1: `localhost:9092`
- broker 2: `localhost:9093`
- broker 3: `localhost:9094`

If your local stack was created before the move to three brokers, existing Kafka topics may still have replication factor `1` because topic creation is idempotent. To fully reprovision the local Kafka cluster with replication factor `3`, recreate the local Kafka state when it is safe to do so:

```bash
docker compose down -v
docker compose up -d --build
```

Pull the LLM model used by the API:

```bash
docker exec -it healthcare-ollama ollama pull llama3.1
```

Optional one-shot validation:

```bash
./scripts/validate_docs.sh
./scripts/validate_stack.sh
./scripts/query_examples.sh
python3 ./scripts/mcp_smoke_test.py
```

## LocalStack

The local stack also includes `localstack` for development scenarios that need an AWS-compatible local endpoint surface.

LocalStack endpoint:

- Edge endpoint: `http://localhost:4566`

Basic health check:

```bash
curl -s http://localhost:4566/_localstack/health | jq .
```

Use this service for local-only integration and smoke testing. It is separate from the production deployment bundle and should not be interpreted as a production AWS configuration pattern.

## Service Endpoints

| Service | URL |
| --- | --- |
| RAG API docs | <http://localhost:8000/docs> |
| RAG API health | <http://localhost:8000/health> |
| RAG API metrics | <http://localhost:8000/metrics> |
| MCP server endpoint | <http://localhost:8000/mcp> |
| MCP diagnostic health | <http://localhost:8000/mcp/health> |
| Provider web app | <http://localhost:8088> |
| Flink UI | <http://localhost:8082> |
| Conduktor Console | <http://localhost:8085> |
| Schema Registry subjects | <http://localhost:8081/subjects> |
| Neo4j Browser | <http://localhost:7474> |
| NeoDash | <http://localhost:5005> |
| Qdrant dashboard | <http://localhost:6333/dashboard> |
| LocalStack edge endpoint | <http://localhost:4566> |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3000> |

## Default Credentials

These credentials are development-only defaults for the local stack. They must not be used as-is in any production or shared environment.

Neo4j:

```text
username: neo4j
password: healthcare123
bolt url: neo4j://localhost:7687
```

Conduktor:

```text
email: admin@healthcare.local
password: Admin@123!
```

Grafana:

```text
username: admin
password: admin123
```

## Verifying Flink Job Submission

The stack should submit exactly one application job by default:

- HealthcareGraphRagPyFlinkJob

Check with:

```bash
curl -s http://localhost:8082/jobs/overview | jq .
```

You should see HealthcareGraphRagPyFlinkJob in RUNNING state and no demo job auto-submission service.

## Conduktor Message View Setup

Because Kafka values are published using Confluent Avro wire format, configure Conduktor topic deserializers as:

- key: `String`
- value: `Avro (Schema Registry)`

If value deserializer is set to `Bytes`, message rendering and masking rules will fail.

## Query Examples

The script scripts/query_examples.sh runs representative GraphRAG queries:

```bash
./scripts/query_examples.sh
```

Direct API call example:

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why might this patient have hyperkalemia risk and what evidence exists?",
    "patient_id": "patient-0001"
  }' | jq .
```

## Project Layout

```text
docs/           Architecture, Kafka contract, graph model, and runbook
docs/adrs/      Architecture Decision Records (ADRs)
flink-app/      PyFlink job, processor logic, and Flink runtime image
mcp-server/     MCP adapter scaffold (reference implementation)
monitoring/     Prometheus, Grafana, alerting, and blackbox config
neo4j/          Constraints and seed graph relationships
producer/       Synthetic event producer
rag-api/        FastAPI GraphRAG API
schemas/        Avro envelope schema
scripts/        Validation and query helper scripts
webapp/         Provider-facing static UI
deploy/         Deployment bundles (production AI runtime and monitoring)
deploy/production/k8s/ Kubernetes-ready AI component manifests
```

## Implementation Notes

- flink-app submits a native PyFlink DataStream job (healthcare_graph_rag_pyflink_job.py) to Flink JobManager.
- healthcare_graph_rag_job.py is retained as a fallback processing implementation and provides reusable sink/enrichment logic consumed by the PyFlink job.
- Schema Registry stores MedicalEvent Avro schemas and Kafka payloads are published with Confluent Avro serialization (schema ID on wire).
- healthcare.dlq.events is created but not actively written by the processor yet.
- API model resolution falls back to available Ollama tags (for example llama3.1:latest) when needed.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/adrs/README.md](docs/adrs/README.md)
- [docs/KAFKA_SCHEMA.md](docs/KAFKA_SCHEMA.md)
- [docs/MCP_LAYER_DESIGN.md](docs/MCP_LAYER_DESIGN.md)
- [docs/NEO4J_MODEL.md](docs/NEO4J_MODEL.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)
- [deploy/production/README.md](deploy/production/README.md)
- [deploy/production/k8s/README.md](deploy/production/k8s/README.md)

## Safety Disclaimer

This project uses synthetic demo data only. It is not clinical software, not a medical device, and not intended for diagnosis, treatment, or patient care.
