# Healthcare GraphRAG Runbook

## Purpose

This runbook covers day-0 and day-2 operations for the local Docker Compose stack, including startup, verification, recovery, and common failure handling.

For production AI-only deployment boundaries and compose bundles, see [deploy/production/README.md](../deploy/production/README.md).

## Prerequisites

- Docker Compose
- curl
- jq

Optional but useful:

- cypher-shell access through the Neo4j container
- Conduktor and Flink dashboards in browser

## Core Commands

Start or refresh services:

```bash
docker compose up -d --build
```

Apply compose changes and remove deleted services:

```bash
docker compose up -d --remove-orphans
```

Stop all services:

```bash
docker compose down
```

Stop and delete volumes (destructive):

```bash
docker compose down -v
```

## Service Health Checklist

### 1) Container Status

```bash
docker compose ps
```

Expected core services: kafka, schema-registry, flink-jobmanager, flink-taskmanager, flink-app, qdrant, neo4j, rag-api, producer.

Note: MCP is embedded in rag-api in the current architecture, so no separate mcp-server container is expected.

### 2) Flink Job Health

```bash
curl -s http://localhost:8082/jobs/overview | jq .
```

Expected steady-state:

- HealthcareGraphRagPyFlinkJob in RUNNING state.
- No demo auto-submit job by default.

### 3) API Health

```bash
curl -s http://localhost:8000/health | jq .
```

Expected response:

```json
{"status":"ok"}
```

### 4) MCP Diagnostic Health

```bash
curl -s http://localhost:8000/mcp/health | jq .
```

Expected response includes:

- status: ok
- mcp.enabled: true
- mcp.endpoint: /mcp

### 5) MCP Handshake Smoke Test

```bash
python3 ./scripts/mcp_smoke_test.py
```

Expected output starts with:

- MCP smoke test passed

### 6) Qdrant Collection

```bash
curl -s http://localhost:6333/collections | jq .
```

Expected collection includes healthcare_events.

### 7) Neo4j Basic Check

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (p:Patient) RETURN count(p) AS patients;'
```

Expected patients count increases over time as producer and stream processing continue.

## Smoke Query

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why might this patient have hyperkalemia risk and what evidence exists?",
    "patient_id": "patient-0001"
  }' | jq .
```

Expected response includes:

- answer
- vector_context
- graph_context
- patients

## Flink Operations

### List Running Jobs

```bash
curl -s http://localhost:8082/jobs/overview | jq '.jobs[] | {jid, name, state}'
```

### Cancel A Job

```bash
curl -s -X PATCH http://localhost:8082/jobs/<job_id>
```

### View Job Exceptions

```bash
curl -s http://localhost:8082/jobs/<job_id>/exceptions | jq .
```

### Inspect Submitter Logs

```bash
docker logs --tail=200 healthcare-flink-app
```

Expected line after successful submission:

- Job has been submitted with JobID ...

## Common Failure Modes And Fixes

### 1) Orphan Container From Removed Service

Symptom:

- docker compose warns about orphan containers from older compose revisions.

Fix:

```bash
docker compose up -d --remove-orphans
```

### 2) Unexpected Non-Healthcare Flink Job Running

Symptom:

- jobs/overview includes old demo job IDs from a previous run.

Fix:

1. Cancel old job:

```bash
curl -s -X PATCH http://localhost:8082/jobs/<demo_job_id>
```

1. Ensure no legacy submitter container exists:

```bash
docker compose ps
```

1. Re-run with orphan cleanup:

```bash
docker compose up -d --remove-orphans
```

### 3) PyFlink Python Worker Not Found

Symptom:

- TaskManager errors about Cannot run program python.

Checks:

```bash
docker exec healthcare-flink-taskmanager which python
docker exec healthcare-flink-taskmanager which python3
```

Expected:

- /usr/bin/python exists as symlink to python3.
- FLINK_PROPERTIES include python.executable and submission uses -Dpython.executable.

Recovery:

```bash
docker compose up -d --build --force-recreate flink-jobmanager flink-taskmanager flink-app
```

### 4) Kafka Connector Class Errors In Flink

Symptom:

- ClassNotFound or NoClassDefFound errors for Kafka connector/runtime classes.

Checks:

```bash
docker exec healthcare-flink-jobmanager ls -1 /opt/flink/lib | grep -E 'flink-connector-kafka|kafka-clients'
```

Recovery:

```bash
docker compose build --no-cache flink-jobmanager flink-taskmanager flink-app
docker compose up -d --force-recreate flink-jobmanager flink-taskmanager flink-app
```

### 5) Ollama Model Not Available

Symptom:

- API answer reports no model installed or model not found.

Fix:

```bash
docker exec -it healthcare-ollama ollama pull llama3.1
```

### 6) Conduktor Message Cannot Be Displayed (Bytes Deserializer)

Symptom:

- `Message cannot be displayed`
- `The data masking rules cannot be applied with bytes deserializer`

Cause:

- Topic value deserializer is set to `Bytes` while payloads are Confluent Avro on wire.

Fix in Conduktor:

1. Set key deserializer to `String`.
1. Set value deserializer to `Avro (Schema Registry)`.
1. Ensure Schema Registry endpoint is `http://schema-registry:8081`.
1. Refresh the topic messages view.

Note:

- `payload_json` is a string field in the current envelope schema.
- Field masking applies to envelope fields, but not nested JSON keys inside `payload_json`.

## Data Reset Procedures

### Soft Restart (keep volumes)

```bash
docker compose down
docker compose up -d --build
```

### Hard Reset (delete all local data)

Warning: this removes Kafka, Qdrant, Neo4j, and Grafana/Prometheus local state.

```bash
docker compose down -v
docker compose up -d --build
```

## Post-Change Validation

After changing compose, streaming code, or docs:

```bash
./scripts/validate_docs.sh
./scripts/validate_stack.sh
curl -s http://localhost:8082/jobs/overview | jq .
```

Confirm:

- docs lint passes,
- stack checks pass,
- only HealthcareGraphRagPyFlinkJob is actively running unless intentionally launching additional jobs.

## Escalation Notes

For persistent stream failures, capture and share:

- docker compose ps
- docker logs --tail=400 healthcare-flink-app
- docker logs --tail=400 healthcare-flink-taskmanager
- `curl -s http://localhost:8082/jobs/overview | jq .`
- `curl -s http://localhost:8082/jobs/JOB_ID/exceptions | jq .`

These artifacts are typically sufficient to identify whether the issue is submission, dependency, connector, or runtime-state related.
