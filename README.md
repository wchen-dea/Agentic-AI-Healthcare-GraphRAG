# Agentic AI Healthcare GraphRAG

Local Docker Compose environment for a healthcare-focused hybrid GraphRAG system built on Kafka, Qdrant, Neo4j, FastAPI, Ollama, and supporting operational tooling.

## Overview

This project simulates a healthcare event platform that:

- generates synthetic clinical, lab, telemetry, pharmacy, claims, and master-data events,
- streams those events through Kafka and Schema Registry,
- enriches transactional events with reference data in the streaming layer,
- writes dual representations to Qdrant and Neo4j,
- serves GraphRAG responses through a FastAPI API backed by Ollama,
- exposes provider, monitoring, and admin interfaces for local exploration.

## What Is Running

```text
Synthetic Producers
  -> Kafka + Schema Registry
  -> Python streaming processor in Flink container
  -> Qdrant vector index
  -> Neo4j property graph
  -> FastAPI GraphRAG API
  -> Ollama local LLM

Supporting tools
  -> Provider web app
  -> NeoDash + Neo4j Browser
  -> Conduktor Console
  -> Prometheus + Grafana + Blackbox Exporter
```

## Key Capabilities

- Hybrid retrieval that combines vector similarity from Qdrant with patient-centric graph context from Neo4j.
- Reference-data enrichment for patients, providers, devices, medications, and payers before sink writes.
- Local observability for Kafka, Flink, Neo4j, and Qdrant.
- Provider-facing UI for issuing RAG queries without using curl.
- Neo4j GUI support through both Neo4j Browser and NeoDash.

## Quick Start

Prerequisites:

- Docker Desktop or Docker Engine with Compose support
- Enough disk for Ollama model download, roughly 5 GB+

Start the stack:

```bash
cd {project_root}/Agentic-AI-Healthcare-GraphRAG
cp .env.example .env
docker compose up --build
```

Pull the local Ollama model used by the API:

```bash
docker exec -it healthcare-ollama ollama pull llama3.1
```

Validate the platform:

```bash
./scripts/validate_docs.sh
./scripts/validate_stack.sh
./scripts/query_examples.sh
```

Notes:

- The first LLM-backed query can take noticeably longer than subsequent calls.

## Endpoints

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

## Credentials And Connection Settings

Neo4j:

```text
username: neo4j
password: healthcare123
bolt url: neo4j://localhost:7687
```

NeoDash:

```text
url: neo4j://localhost:7687
username: neo4j
password: healthcare123
```

NeoDash is preconfigured in `docker-compose.yml` and should connect to the local Neo4j instance directly.

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

## Example Queries

The included [scripts/query_examples.sh](scripts/query_examples.sh) script runs five representative GraphRAG queries:

```bash
# 1) Hyperkalemia risk evidence
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Why might this patient have hyperkalemia risk and what evidence exists?","patient_id":"patient-0001"}'

# 2) Vitals instability and respiratory concern
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize recent device telemetry anomalies for this patient and whether they suggest respiratory deterioration.","patient_id":"patient-0012"}'

# 3) Medication interaction and safety
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Check current medication orders for possible interaction risks and provide supporting graph and event evidence.","patient_id":"patient-0025"}'

# 4) Clinical vs claims consistency
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Compare clinical events with claim status for this patient and identify any potential documentation or coverage mismatch.","patient_id":"patient-0007"}'

# 5) Cross-patient cohort risk overview
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Across recent events, which patterns indicate rising cardiometabolic risk and what evidence is most frequent?"}'
```

## Provider Web App

The provider UI is a lightweight static web application that calls the FastAPI backend from the browser.

Features:

- configurable API base URL,
- optional patient ID filter,
- free-text clinical question input,
- structured display for answer, vector context, and graph context,
- browser-local persistence of the selected API base URL.

## Monitoring And Operations

Observability components:

- Prometheus scrapes Qdrant directly and probes Neo4j, Kafka, and Flink through Blackbox Exporter.
- Grafana auto-loads two dashboards:
  - `monitoring/grafana/dashboards/healthcare-monitoring-overview.json`
  - `monitoring/grafana/dashboards/kafka-flink-service-health.json`
- Prometheus alert rules are defined in `monitoring/prometheus-alerts.yml`.
- Conduktor provides Kafka topic, broker, and schema visibility.

Operational validation commands:

```bash
./scripts/validate_docs.sh
docker compose ps
./scripts/validate_stack.sh
./scripts/query_examples.sh
```

## Project Layout

```text
docs/           Architecture, Kafka contract, and graph model docs
flink-app/      Streaming processor container and processing logic
monitoring/     Prometheus, Grafana, alerting, and probe config
neo4j/          Constraints and seed graph relationships
producer/       Synthetic event producer
rag-api/        FastAPI GraphRAG API
schemas/        Avro envelope schema
scripts/        Validation and example query scripts
webapp/         Provider-facing static UI
```

## Implementation Notes

- The `flink-app` service is not a native PyFlink DataStream job. It is a Python Kafka consumer running inside a Flink-oriented container and following Flink-style streaming principles.
- Schema Registry is used to register a shared Avro envelope, but the producer currently publishes JSON messages for local transparency and simpler Python handling.
- A DLQ topic is created in Kafka for future hardening, but this MVP does not yet implement a dedicated dead-letter writer.
- The RAG API automatically falls back to an available Ollama model variant when possible, for example `llama3.1` vs `llama3.1:latest`.

## Additional Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/KAFKA_SCHEMA.md](docs/KAFKA_SCHEMA.md)
- [docs/NEO4J_MODEL.md](docs/NEO4J_MODEL.md)

## Safety Disclaimer

This project uses synthetic demo data only. It is not clinical software, not a medical device, and not intended for diagnosis, treatment, or patient care.
