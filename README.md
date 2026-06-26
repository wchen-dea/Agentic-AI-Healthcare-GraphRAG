# Agentic AI Healthcare GraphRAG

A healthcare-focused hybrid GraphRAG system built on Kafka, PyFlink, Qdrant, Neo4j, FastAPI, and Ollama.

## Summary

This project provides a healthcare AI platform blueprint across three dimensions:

- Technical leadership: streaming-first ingestion, dual evidence stores (vector plus graph), and agent-ready APIs (REST + MCP) on shared reasoning logic.
- Industry innovation: one reusable architecture for clinical, operational, and financial healthcare AI workflows.
- Implementation maturity: complete local development stack plus production-ready deployment variants for AI deliverables.

Production boundary in this repository:

- In scope: rag-api (embedded MCP), provider-web, optional standalone mcp-server, separate monitoring config.
- Out of scope: source data systems, Confluent Kafka platform, and Apache Flink platform (independently managed).

## Tech Stack

- Streaming: Apache Kafka, Confluent Schema Registry, Apache Flink (PyFlink)
- Data Stores: Qdrant (vector), Neo4j (graph)
- API and AI: FastAPI, Ollama (local), Anthropic/OpenAI ready via provider routing
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
| Medication Safety | Orders, allergies, interaction knowledge | Safer prescribing, interaction explainability |
| Device and Remote Monitoring | Device telemetry, alerts, maintenance events | Faster anomaly response, operational efficiency |

## Innovation Highlights

- Real-time healthcare intelligence stack: Kafka + Flink processing with Avro schema-governed event contracts.
- Hybrid GraphRAG retrieval: Qdrant vector evidence plus Neo4j relationship context in one grounded answer flow.
- Streaming enrichment pattern: reference/master data fused into transactional events before vector and graph persistence.
- Production-ready AI portability: local Ollama by default with clear provider-routing path to Anthropic/OpenAI.
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
- Production path: provider routing for Anthropic or OpenAI via LLM_PROVIDER and LLM_MODEL.
- Recommended controls: LLM_TIMEOUT_SECONDS, LLM_MAX_TOKENS, LLM_TEMPERATURE.
- Security: inject API keys from a secret manager, never from source-controlled files.

## Key Capabilities

- Hybrid retrieval that combines semantic nearest-neighbor evidence from Qdrant with patient-centric relationship context from Neo4j.
- Reference-data enrichment for patients, providers, devices, medications, and payers before sink writes.
- Native Flink job visibility from the Flink dashboard.
- Local observability for Kafka, Flink, Neo4j, and Qdrant.
- Provider-facing UI for query workflows without curl.
- Embedded MCP tool endpoint in rag-api for agent integration without a separate MCP service.

## MCP Quick Verify

```bash
curl -s http://localhost:8000/mcp/health | jq .
python3 ./scripts/mcp_smoke_test.py
```

## Quick Start

Prerequisites:

- Docker Desktop or Docker Engine with Compose support
- jq (recommended for shell validations)
- Enough disk for Ollama model download (roughly 5 GB+)

Start the full stack:

```bash
cd /path/to/Agentic-AI-Healthcare-GraphRAG
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

## Service Endpoints

| Service | URL |
| --- | --- |
| RAG API docs | <http://localhost:8000/docs> |
| RAG API health | <http://localhost:8000/health> |
| MCP server endpoint | <http://localhost:8000/mcp> |
| MCP diagnostic health | <http://localhost:8000/mcp/health> |
| Provider web app | <http://localhost:8088> |
| Flink UI | <http://localhost:8082> |
| Conduktor Console | <http://localhost:8085> |
| Schema Registry subjects | <http://localhost:8081/subjects> |
| Neo4j Browser | <http://localhost:7474> |
| NeoDash | <http://localhost:5005> |
| Qdrant dashboard | <http://localhost:6333/dashboard> |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3000> |

## Default Credentials

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
