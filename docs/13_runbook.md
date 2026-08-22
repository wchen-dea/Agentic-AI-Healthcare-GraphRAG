# Healthcare GraphRAG Runbook

## Purpose

This runbook covers day-0 and day-2 operations for the local Docker Compose development stack, including startup, verification, recovery, and common failure handling.

For production AI-only deployment boundaries and compose bundles, see [deploy/README.md](../deploy/README.md).

Scope note:

- The commands and defaults in this runbook are for local development and synthetic-demo operation.
- Production-ready deployment configuration lives under `deploy/` and should be operated with environment-specific security, secrets, networking, and platform controls.
- For full deployment documentation including Helm charts, see [deploy/README.md](../deploy/README.md).

## Prerequisites

- Docker Compose
- [uv](https://docs.astral.sh/uv/) (Python project manager)
- curl
- jq
- make (for Makefile shortcuts)
- Helm 3 (for Kubernetes deployments)
- minikube (for local Kubernetes)

Optional but useful:

- cypher-shell access through the Neo4j container
- Conduktor and Flink dashboards in browser

## Makefile Quick Reference

```bash
make up          # Start infra + healthcare + supply-chain
make up-hc       # Start infra + healthcare only
make down-all    # Stop everything
make ps          # Show running containers
make neo4j-hc    # Healthcare cypher-shell
make neo4j-sc    # Supply-chain cypher-shell
make test-hc     # Run healthcare tests
make topics      # List Kafka topics
make clean       # Full cleanup with volume removal
make validate-skills  # Validate agent skills for both domains
make generate-skills  # Regenerate skill packages
make validate-ontology # Validate ontology configs
make helm-dev    # Deploy to minikube via Helm
make helm-dev-down # Tear down minikube release
make helm-ports  # Start all port-forwards
make helm-ports-stop # Kill all port-forwards
make helm-lint   # Lint Helm chart + template both envs
make helm-prd    # Render production Helm templates (dry-run)
make help        # Show all targets
```

## Core Commands

Start or refresh services:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build
```

Start supply-chain domain alongside healthcare:

```bash
docker compose -f container/docker-compose.infra.yml \
  -f container/docker-compose.healthcare.yml \
  -f container/docker-compose.supply-chain.yml \
  up -d --build
```

Apply compose changes and remove deleted services:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --remove-orphans
```

If you change `rag-api` source code, rebuild the image before recreating the service:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml build rag-api
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --force-recreate rag-api
```

### Optional: Enable ReAct Loop In Local `rag-api`

Add or update these variables in `.env`:

```bash
RAG_API_REACT_ENABLED=true
RAG_API_REACT_MAX_ITERS=3
RAG_API_REACT_MIN_CONFIDENCE=0.75
RAG_API_REACT_MAX_NO_PROGRESS_STEPS=1
```

Rebuild and recreate `rag-api`:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml build rag-api
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --force-recreate rag-api
```

Verify with a smoke query and ensure a `react` object is present in the response:

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize hyperkalemia risk","patient_id":"patient-0001"}' | jq '.react'
```

Expected: non-null object with `enabled`, `iterations`, and `final_reason`.

### Optional: Enable LangGraph Multi-Agent Mode

Add or update these variables in `.env`:

```bash
RAG_API_LANGGRAPH_ENABLED=true
LANGGRAPH_MAX_ITERATIONS=3
```

Rebuild and recreate `rag-api`:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml build rag-api
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --force-recreate rag-api
```

Verify with a smoke query and ensure a `langgraph` object is present in the response:

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize hyperkalemia risk","patient_id":"patient-0001"}' | jq '.langgraph'
```

Expected: non-null object with `enabled`, `iterations`, `final_reason`, `confidence`, and `agent_trace`.

LangGraph takes priority over ReAct when both are enabled. See [10_langgraph_comparison.md](10_langgraph_comparison.md) for details.

### Optional: Enable MLflow Tracing

Add or update these variables in `.env`:

```bash
MLFLOW_TRACKING_URI=http://mlflow:5000
MLFLOW_EXPERIMENT_NAME=healthcare-graphrag
```

Rebuild and recreate `rag-api`:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml build rag-api
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --force-recreate rag-api
```

Verify MLflow UI is reachable:

```bash
curl -s http://localhost:5000/health
```

After running queries, traces appear in the MLflow Tracing UI at http://localhost:5000. Tracing works for all three query modes (single-pass, ReAct, LangGraph).

Run only ReAct and planner test suites (CI-safe shortcut):

```bash
./domains/healthcare/scripts/test_react_planner.sh
```

Stop all services:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml down
```

Stop and delete volumes (destructive):

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml down -v
```

## Service Health Checklist

### 1) Container Status

```bash
make ps  # or: docker compose -f container/docker-compose.infra.yml -p infra ps
```

Expected core services: kafka, kafka2, kafka3, schema-registry, flink-jobmanager, flink-taskmanager, flink-app, qdrant, neo4j, rag-api, producer, localstack.

Note: MCP is embedded in the agents service in the current architecture; MCP is embedded in the agents process.

Producer startup is intentionally blocked until `schema-registry` is healthy and `kafka-init` completes successfully.

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
python3 ./domains/healthcare/scripts/mcp_smoke_test.py
```

Expected output starts with:

- MCP smoke test passed

### 5a) Skills Layer Plan Endpoint Check

```bash
curl -s -X POST http://localhost:8000/skills/plan \
  -H "Content-Type: application/json" \
  -H "X-Caller-Role: read_only" \
  -d '{"business_goal":"medication_safety_review"}' | jq .
```

Expected response includes:

- `business_goal`
- `agent`
- `skills`
- `mcp_tools`
- `runtime_tools`

### 6) Qdrant Collection

```bash
curl -s http://localhost:6333/collections | jq .
```

Expected collection includes healthcare_events.

### 7) LocalStack Health

```bash
curl -s http://localhost:4566/_localstack/health | jq .
```

Expected response includes a LocalStack version plus a services object with available local AWS-compatible services.

### 8) Neo4j Basic Check

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (p:Patient) RETURN count(p) AS patients;'
```

Expected patients count increases over time as producer and stream processing continue.

### 8a) Drug Safety Seeding Verification

Verify `init.cypher` seeded the FAERS-aligned pharmacovigilance vocabulary:

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (ao:AdverseOutcome) RETURN ao.code, ao.description ORDER BY ao.code;'
```

Expected: 6 rows — CA, DE, DS, HO, LT, OT.

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (:Medication)-[r:HAS_KNOWN_REACTION]->(:Symptom) RETURN count(r) AS edges;'
```

Expected: 20 or more edges.

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (m:Medication)-[r:CONTRAINDICATED_FOR]->(c:Condition) RETURN m.name, c.name, r.severity ORDER BY r.severity DESC LIMIT 8;'
```

Expected rows include: Metformin → Chronic Kidney Disease, Lisinopril → Hyperkalemia, Vancomycin → Chronic Kidney Disease.

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (m:Medication)-[r:INTERACTS_WITH]->(m2:Medication) WHERE r.mechanism IS NOT NULL RETURN m.name, m2.name, r.mechanism LIMIT 5;'
```

Expected rows include Warfarin interactions with mechanism annotations.

### 8b) Live Adverse Event and Lab Signal Check

After the stack has been running for a few minutes:

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication) RETURN m.name, ae.symptom_name, ae.severity LIMIT 10;'
```

Expected: rows appear as clinical notes with matching symptoms are processed.

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (o:Observation)-[mi:MAY_INDICATE]->(c:Condition) RETURN o.name, o.value, c.name, mi.reason LIMIT 10;'
```

Expected: rows appear as lab results cross clinical thresholds.

### 9) RAG API Metrics Endpoint

```bash
curl -s http://localhost:8000/metrics | grep -E 'rag_api_(http_request_duration_seconds|tool_execution_duration_seconds|tool_execution_total)'
```

Expected result includes metric families:

- rag_api_http_request_duration_seconds
- rag_api_tool_execution_duration_seconds
- rag_api_tool_execution_total

### 10) Grafana Query Latency Panel

In Grafana, open the Healthcare GraphRAG Monitoring Overview dashboard and verify the panel:

- RAG Query Latency (p50/p95)

The panel uses the query tool histogram and should display two series:

- query p50
- query p95

### 11) MLflow Tracing Health (when enabled)

```bash
curl -s http://localhost:5000/health
```

Expected: HTTP 200. If the MLflow container is running, traces are viewable at http://localhost:5000.

Verify traces are being recorded after a query:

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{"question":"Summarize hyperkalemia risk","patient_id":"patient-0001"}' > /dev/null
# Then check MLflow UI for new trace spans
```

## Smoke Query

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why might this patient have hyperkalemia risk and what evidence exists?",
    "patient_id": "patient-0001"
  }' | jq .
```

Expected top-level response fields:

- `answer` — LLM-generated text grounded in both retrieval paths
- `vector_context` — list of Qdrant ANN hits, each with `event_type`, `score`, `text_redacted`
- `patients` — patient IDs resolved from vector hits plus the supplied `patient_id`
- `trace_id`, `retrieved_at`, `guardrails`

Each entry in `graph_context` contains:

| Field | Content |
| --- | --- |
| `conditions` | Diagnosed conditions with onset timestamps |
| `symptoms` | Symptoms extracted from clinical notes |
| `observations` | Lab results with `lab_panel` and `specimen_type` |
| `medications` | Orders with `drug_class`, `route`, `order_type` |
| `interactions` | Drug-drug pairs with `risk`, `severity`, `mechanism` |
| `vitals` | Device readings with `temp_c`, `rr`, `alert` |
| `claims` | Claims with `Procedure` description and `Payer` name |
| `lab_signals` | `MAY_INDICATE` edges: observation → indicated condition |
| `icd10_codes` | `CODED_AS` edges: condition → ICD-10 code |
| `adverse_events` | `REPORTED_ADVERSE_REACTION` with medication, MedDRA term, severity |
| `contraindications` | `CONTRAINDICATED_FOR` edges active for current medication orders |

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

## Skills Package Operations

Generate Agent Skills package files from the runtime skills layer config:

```bash
python domains/healthcare/scripts/generate_agent_skills.py
python domains/supply-chain/scripts/generate_agent_skills.py
```

Check for drift without modifying files:

```bash
python domains/healthcare/scripts/generate_agent_skills.py --check
python domains/supply-chain/scripts/generate_agent_skills.py --check
```

Validate generated skill folders and SKILL.md frontmatter:

```bash
python domains/healthcare/scripts/validate_agent_skills.py
python domains/supply-chain/scripts/validate_agent_skills.py
```

## Common Failure Modes And Fixes

### 1) Orphan Container From Removed Service

Symptom:

- docker compose warns about orphan containers from older compose revisions.

Fix:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --remove-orphans
```

### 2) Unexpected Non-Healthcare Flink Job Running

Symptom:

- jobs/overview includes old demo job IDs from a previous run.

Fix:

1. Cancel old job:

```bash
curl -s -X PATCH http://localhost:8082/jobs/<demo_job_id>
```

2. Ensure no legacy submitter container exists:

```bash
make ps  # or: docker compose -f container/docker-compose.infra.yml -p infra ps
```

3. Re-run with orphan cleanup:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --remove-orphans
```

### 3) PyFlink Python Worker Not Found

Symptom:

- TaskManager errors about Cannot run program python.

Checks:

```bash
docker exec infra-flink-taskmanager which python
docker exec infra-flink-taskmanager which python3
```

Expected:

- /usr/bin/python exists as symlink to python3.
- FLINK_PROPERTIES include python.executable and submission uses -Dpython.executable.

Recovery:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build --force-recreate flink-jobmanager flink-taskmanager flink-app
```

### 4) Kafka Connector Class Errors In Flink

Symptom:

- ClassNotFound or NoClassDefFound errors for Kafka connector/runtime classes.

Checks:

```bash
docker exec infra-flink-jobmanager ls -1 /opt/flink/lib | grep -E 'flink-connector-kafka|kafka-clients'
```

Recovery:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml build --no-cache flink-jobmanager flink-taskmanager flink-app
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --force-recreate flink-jobmanager flink-taskmanager flink-app
```

### 5) Ollama Model Not Available

Symptom:

- API answer reports no model installed or model not found.
- In dev/local environments using Ollama as `LLM_PROVIDER`.

Fix (Docker Compose):

```bash
docker exec -it infra-ollama ollama pull llama3.1
```

Fix (Minikube/Helm):

```bash
kubectl -n healthcare-ai-dev exec deploy/ollama -- ollama pull llama3.1
```

Note: Production uses OpenAI (primary) with Anthropic (fallback) — Ollama is not deployed. If both cloud providers fail, check `OPENAI_API_KEY` and `ANTHROPIC_API_KEY` secrets.

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
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml down
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build
```

### Hard Reset (delete all local data)

Warning: this removes Kafka, Qdrant, Neo4j, and Grafana/Prometheus local state.

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml down -v
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build
```

## Post-Change Validation

After changing compose, streaming code, or docs:

```bash
./scripts/validate_docs.sh
./scripts/validate_all_stacks.sh
make validate-skills
make validate-ontology
curl -s http://localhost:8082/jobs/overview | jq .
```

For Helm deployments:

```bash
helm template dev deploy/helm -f deploy/helm/values-dev.yaml > /dev/null && echo OK
helm template prd deploy/helm -f deploy/helm/values-production.yaml > /dev/null && echo OK
```

Confirm:

- docs lint passes,
- stack checks pass,
- only HealthcareGraphRagPyFlinkJob is actively running unless intentionally launching additional jobs.

## Kubernetes / Helm Operations

### Deploy dev (minikube)

```bash
./deploy/dev/setup-minikube.sh
# Or manually:
minikube start --cpus=4 --memory=8192
helm install healthcare-dev deploy/helm -f deploy/helm/values-dev.yaml -n healthcare-ai-dev --create-namespace
```

### Deploy production

```bash
helm install healthcare deploy/helm \
  -f deploy/helm/values-production.yaml \
  -n healthcare-ai --create-namespace \
  --set rag-api.secrets.NEO4J_PASSWORD=<value> \
  --set rag-api.secrets.OPENAI_API_KEY=<value> \
  --set rag-api.secrets.ANTHROPIC_API_KEY=<value>
```

### Upgrade

```bash
helm upgrade healthcare deploy/helm -f deploy/helm/values-production.yaml -n healthcare-ai
```

### Rollback

```bash
helm rollback healthcare 1 -n healthcare-ai
```

### Check pod health

```bash
kubectl -n healthcare-ai-dev get pods
kubectl -n healthcare-ai-dev logs deploy/rag-api --tail=50
kubectl -n healthcare-ai-dev exec deploy/rag-api -- curl -s localhost:8000/health
```

### Tear down dev

```bash
make helm-dev-down
minikube delete
```

### Port-forwards (macOS Docker driver)

On macOS with Docker driver, NodePorts are not directly accessible. Use port-forwards:

```bash
make helm-ports       # start all port-forwards
make helm-ports-stop  # kill all port-forwards
```

Services:
- RAG API: `http://localhost:8000`
- Web UI: `http://localhost:8088`
- Neo4j: `http://localhost:7474`
- Qdrant: `http://localhost:6333/dashboard`
- Conduktor: `http://localhost:9080`

### Minikube Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `K8S_APISERVER_MISSING` on start | Stale cluster state | `minikube delete && make helm-dev` |
| Confluent pods crash: "PORT is deprecated" | Kubernetes service-linked env vars | `enableServiceLinks: false` on pod spec (already set in charts) |
| Neo4j crash: "Unrecognized setting PORT" | Same service-link env var injection | Same fix |
| Ollama OOM killed | Not enough memory for model | Default is 16GB; use `MINIKUBE_MEMORY=20480 make helm-dev` for llama3.1 |
| `ImagePullBackOff` | Image not built in minikube's Docker | `eval $(minikube docker-env) && docker build ...` (setup-minikube.sh does this automatically) |
| Flink blob transfer timeout | Missing port 6124 on jobmanager service | Already fixed in chart |
| Query takes 2-3 minutes | CPU-only LLM inference | Expected for qwen2.5:1.5b; use Docker Compose for GPU/Metal acceleration |
| Port-forward dies mid-request | kubectl limitation with long connections | Re-run `make helm-ports` |

### Minimum Requirements (Minikube)

- Docker Desktop: allocate at least 16GB RAM to Docker engine
- `minikube start --cpus=4 --memory=16384`
- Disk: ~10GB for images + model weights

## LLM Provider Troubleshooting

| Env | Provider | Symptom | Check |
|-----|----------|---------|-------|
| Dev | Ollama | "no models installed" | `ollama pull llama3.1` in the ollama pod/container |
| Prod | OpenAI | "OPENAI_API_KEY not set" | Verify secret injection via `kubectl get secret rag-api-secrets -o yaml` |
| Prod | Anthropic (fallback) | "ANTHROPIC_API_KEY not set" | Same — check secret |
| Prod | Both fail | "LLM error" in answer | Check network egress to `api.openai.com` and `api.anthropic.com` |

## Escalation Notes

For persistent stream failures, capture and share:

- docker compose ps
- docker logs --tail=400 healthcare-flink-app
- docker logs --tail=400 infra-flink-taskmanager
- `curl -s http://localhost:8082/jobs/overview | jq .`
- `curl -s http://localhost:8082/jobs/JOB_ID/exceptions | jq .`

These artifacts are typically sufficient to identify whether the issue is submission, dependency, connector, or runtime-state related.
