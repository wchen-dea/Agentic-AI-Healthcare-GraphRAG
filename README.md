# Agentic AI Healthcare GraphRAG

Local Docker Compose environment for a healthcare-focused hybrid GraphRAG system built on Kafka, PyFlink, Qdrant, Neo4j, FastAPI, and Ollama.

## Tech Stack

- Streaming: Apache Kafka, Confluent Schema Registry, Apache Flink (PyFlink)
- Data Stores: Qdrant (vector), Neo4j (graph)
- API and AI: FastAPI, Ollama (local), Anthropic/OpenAI ready via provider routing
- Frontend: Static provider web app (Nginx-served)
- Observability: Prometheus, Grafana, Blackbox Exporter
- Operations and Tooling: Docker Compose, Conduktor, NeoDash

## Overview

This project simulates an end-to-end healthcare intelligence pipeline that:

- generates synthetic transactional and reference healthcare events,
- streams events through Kafka and Schema Registry,
- processes streams in a native PyFlink DataStream job,
- enriches transactional events with master data,
- writes dual sinks to Qdrant and Neo4j,
- serves GraphRAG responses through a FastAPI API backed by Ollama,
- exposes provider and observability surfaces for local exploration.

## Industry Extensions

This project is designed as a reusable healthcare intelligence platform, not a single fixed workflow.

Why it extends broadly:

- The platform layer stays stable (streaming, storage, retrieval, API, observability).
- New healthcare sections are added as domain modules (topic contracts, enrichment rules, graph entities, prompt templates).
- Expansion is mostly configuration and modeling, rather than full-system rewrites.

| Healthcare Section | Example Data Sources | Typical Outcomes |
| --- | --- | --- |
| Clinical Operations | EHR notes, labs, telemetry | Earlier risk detection, clinician-ready summaries |
| Revenue Cycle | Claims, coding events, prior-auth records | Denial reduction, coding consistency insights |
| Payer and Utilization | Claims timelines, authorization decisions | Utilization trend detection, anomaly triage |
| Population Health | Longitudinal encounters, chronic-condition signals | Cohort risk stratification, outreach prioritization |
| Medication Safety | Orders, allergies, interaction knowledge | Safer prescribing, interaction explainability |
| Device and Remote Monitoring | Device telemetry, alerts, maintenance events | Faster anomaly response, operational efficiency |

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

## LLM Selection: Local vs Production

### Local Development (Current Default)

The current implementation uses Ollama through the RAG API environment settings:

- OLLAMA_URL (default: <http://ollama:11434>)
- OLLAMA_MODEL (default: llama3.1)

This is the recommended mode for local testing because it avoids external API dependencies and keeps data fully local.

### Production Deployment (Anthropic or OpenAI)

For production, use a provider abstraction in the API layer and route generation calls to a managed model provider.

- Anthropic option: use a provider adapter that calls the Anthropic Messages API.
- OpenAI option: use a provider adapter that calls the OpenAI Responses or Chat Completions API.

Recommended selection policy:

- Primary provider chosen by configuration.
- Optional fallback provider for resiliency.
- Per-environment model mapping (for example, fast model for triage, higher-quality model for final response).

Recommended production environment variables:

- LLM_PROVIDER: ollama, anthropic, or openai
- LLM_MODEL: provider-specific model name
- LLM_TIMEOUT_SECONDS: request timeout budget
- LLM_MAX_TOKENS: output guardrail
- LLM_TEMPERATURE: generation control

Provider-specific secrets should be injected via your secret manager, not stored in source control.

## Key Capabilities

- Hybrid retrieval that combines semantic nearest-neighbor evidence from Qdrant with patient-centric relationship context from Neo4j.
- Reference-data enrichment for patients, providers, devices, medications, and payers before sink writes.
- Native Flink job visibility from the Flink dashboard.
- Local observability for Kafka, Flink, Neo4j, and Qdrant.
- Provider-facing UI for query workflows without curl.

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
```

## Service Endpoints

| Service | URL |
| --- | --- |
| RAG API docs | <http://localhost:8000/docs> |
| RAG API health | <http://localhost:8000/health> |
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
flink-app/      PyFlink job, processor logic, and Flink runtime image
monitoring/     Prometheus, Grafana, alerting, and blackbox config
neo4j/          Constraints and seed graph relationships
producer/       Synthetic event producer
rag-api/        FastAPI GraphRAG API
schemas/        Avro envelope schema
scripts/        Validation and query helper scripts
webapp/         Provider-facing static UI
```

## Implementation Notes

- flink-app submits a native PyFlink DataStream job (healthcare_graph_rag_pyflink_job.py) to Flink JobManager.
- healthcare_graph_rag_job.py is retained as a fallback processing implementation and provides reusable sink/enrichment logic consumed by the PyFlink job.
- Schema Registry stores the MedicalEvent Avro schema; producer wire payloads remain JSON for MVP readability.
- healthcare.dlq.events is created but not actively written by the processor yet.
- API model resolution falls back to available Ollama tags (for example llama3.1:latest) when needed.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/KAFKA_SCHEMA.md](docs/KAFKA_SCHEMA.md)
- [docs/NEO4J_MODEL.md](docs/NEO4J_MODEL.md)
- [docs/RUNBOOK.md](docs/RUNBOOK.md)

## Safety Disclaimer

This project uses synthetic demo data only. It is not clinical software, not a medical device, and not intended for diagnosis, treatment, or patient care.
