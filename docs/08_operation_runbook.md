# 08 — Operations Runbook

How to run, check, observe and recover the platform, both on Docker Compose and on Kubernetes. Design background is in [02 — Architecture](02_architecture.md) and [03 — Platform Blueprint](03_platform_blueprint.md). Pipeline details are in [04 — Data Platform](04_data_platform.md), and agent behaviour is in [05 — AI Agents](05_ai_agents.md).

All commands run from the repository root. Credentials come from the environment, for example `$NEO4J_PASSWORD`. Never paste them into tickets or logs.

## 1. Prerequisites and service map

Prerequisites:

- Docker Desktop (or Docker Engine with Compose v2), with at least 16 GB RAM, 4 CPUs and about 10 GB of free disk
- `uv` and Python 3.11 for tests and tooling
- Node.js for the healthcare web UI dev server
- For Kubernetes: `minikube`, `kubectl` and `helm`

The stack is made of three Compose projects that share the external network `graphrag-net`:

| Make variable | Project | Compose file | Container prefix |
| --- | --- | --- | --- |
| `DC_INFRA` | `infra` | `infra/compose/docker-compose.infra.yml` | `infra-` |
| `DC_HC` | `healthcare` | `infra/compose/docker-compose.healthcare.yml` | `healthcare-` |
| `DC_SC` | `supplychain` | `infra/compose/docker-compose.supply-chain.yml` | `supplychain-` |

Host ports:

| Service | Port(s) | Notes |
| --- | --- | --- |
| Healthcare agent API | 8000 | `/docs` for OpenAPI |
| Supply-chain agent API | 8001 | |
| Healthcare web UI | 8088 | |
| Supply-chain web UI | 8089 | |
| Qdrant (healthcare) | 6333, 6334 | REST and gRPC |
| Qdrant (supply chain) | 6335, 6336 | REST and gRPC |
| Neo4j (healthcare) | 7474, 7687 | Browser and Bolt |
| Neo4j (supply chain) | 7475, 7688 | Browser and Bolt |
| Flink UI (healthcare) | 8082 | |
| Flink UI (supply chain) | 8083 | |
| Kafka | 9092–9094 (host), 29092–29094 (in-network) | Three brokers |
| ZooKeeper | 2181 | |
| Schema Registry | 8081 | |
| Conduktor Console | 8085 | 9080 when port-forwarded from Kubernetes |
| Ollama | 11434 | |
| MLflow | 5000 | |
| Prometheus | 9090 | |
| Blackbox exporter | 9115 | |
| Grafana | 3000 | |
| LocalStack | 4566 | |

## 2. Lifecycle

Run `make help` for the full target list. Choose one local deployment path per environment.

### Docker Compose-only path

All services run as Docker containers on `graphrag-net`:

```bash
make compose-up       # full stack
make compose-up-hc    # healthcare only
make compose-down
```

Use `make ps`, `make validate`, `make api-hc`, and `make mlflow` for checks. This path uses host ports directly, including the healthcare API on port 8000.

### Minikube-in-Docker path

Minikube runs with the Docker driver; workloads run as Kubernetes pods inside the Minikube node:

```bash
make minikube-up
make minikube-ports
# use localhost:8000 and localhost:8088
make minikube-ports-stop
make minikube-down
```

Required tools are Docker, `minikube`, `kubectl`, and `helm`. The setup script builds images after `minikube docker-env` is applied, so Kubernetes uses local images rather than pulling them from a registry. Inspect this path with:

```bash
kubectl -n healthcare-ai-dev get pods
kubectl -n healthcare-ai-dev get events --sort-by=.lastTimestamp
```

Use `minikube delete` for a full cluster reset. Do not use `make compose-down` to tear down Minikube workloads.

### Existing lifecycle aliases

| Task | Command |
| --- | --- |
| Start infra and both domains | `make up` |
| Start infra and one domain | `make up-hc` or `make up-sc` |
| Pull the local LLM | `make pull-model` (`llama3.1` into `infra-ollama`) |
| Build images | `make build` (healthcare), `make build-sc`, `make build-all` |
| Restart one domain | `make restart` (healthcare) or `make restart-sc` |
| Stop everything | `make down` (uses `--remove-orphans`) |
| Wipe volumes and prune | `make clean` |
| Rebuild from scratch | `make fresh` (`clean`, `up`, `pull-model`) |
| Container status | `make ps` |
| Follow logs | `make logs` (healthcare) or `make logs-sc` |
| List Kafka topics | `make topics` |

Resets:

- **Soft reset** keeps data: `make down && make up`.
- **Hard reset** deletes Neo4j, Qdrant, Kafka and MLflow volumes: `make clean && make up && make pull-model`. The `neo4j-init` containers re-seed the ontology and the producers repopulate the stores.

## 3. Health checklist

Run these after every start or deployment. `make validate` runs the scripted equivalent (`scripts/validate_all_stacks.sh`).

| Check | Command | Expect |
| --- | --- | --- |
| Agent APIs | `make api-hc`, `make api-sc` | `status` is `ok` |
| MCP endpoint | `curl -s localhost:8000/mcp/health` | `mcp.enabled` is true and the endpoint is `/mcp` |
| MCP tools end to end | `python3 domains/healthcare/scripts/mcp_smoke_test.py` | All tools listed and callable |
| Skill planner | see below | A plan for `medication_safety_review` |
| Flink jobs | `make flink-hc`, `make flink-sc` | One `RUNNING` job per domain |
| Qdrant collections | `make qdrant-hc`, `make qdrant-sc` | `points_count` grows; vector size matches the embedding provider (384 for MiniLM, 1024 for Databricks GTE) |
| Neo4j | `make neo4j-hc`, `make neo4j-sc` | Cypher shell opens |
| MLflow | `make mlflow` | `OK` |
| LocalStack | `curl -s localhost:4566/_localstack/health` | Services listed |

Skill planner check:

```bash
curl -s -X POST localhost:8000/skills/plan \
  -H 'Content-Type: application/json' \
  -H 'X-Caller-Role: read_only' \
  -d '{"business_goal":"medication_safety_review"}'
```

Healthcare Neo4j seed checks:

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (o:AdverseOutcome) RETURN o.code ORDER BY o.code"
# expect CA, DE, DS, HO, LT, OT

docker exec healthcare-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH ()-[r:HAS_KNOWN_REACTION]->() RETURN count(r)"
# expect at least 20

docker exec healthcare-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (m:Medication)-[:CONTRAINDICATED_FOR]->(c) RETURN m.name, c.name"
# includes Metformin→CKD, Lisinopril→Hyperkalemia, Vancomycin→CKD
```

Live-data checks, once the producer has run for a minute:

```bash
docker exec healthcare-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (:AdverseEvent)-[r:ASSOCIATED_WITH_MEDICATION]->() RETURN count(r)"
docker exec healthcare-neo4j cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH ()-[r:MAY_INDICATE]->() RETURN count(r)"
```

`neo4j-init` verifies edge counts after seeding. If it logs `Could not read ... edge count (got: ''); skipping verification`, the count query returned no output. The seed itself is fine; run the queries above by hand to confirm.

## 4. Smoke queries

```bash
curl -s -X POST localhost:8000/query \
  -H 'Content-Type: application/json' \
  -d '{"question":"Summarize recent adverse events for this patient","patient_id":"patient-0001"}'
```

The response holds `answer`, `vector_context`, `graph_context`, `patients`, `trace_id`, `retrieved_at`, `guardrails` and `langgraph` (`enabled`, `iterations`, `final_reason`, `confidence`, `agent_trace`). The full field list is in [05 — AI Agents](05_ai_agents.md#8-http-api).

More examples: `make query-hc` and `make query-sc`, which run `domains/*/scripts/query_examples.sh`.

## 5. Observability

| Tool | Where | What to look at |
| --- | --- | --- |
| Prometheus | `localhost:9090` | Scrapes every 15 s. Jobs: `qdrant`, `agent_service`, `neo4j_probe`, `kafka_probe`, `flink_probe` |
| Blackbox exporter | `localhost:9115` | `http_2xx` and `tcp_connect` probes, 5 s timeout |
| Grafana | `localhost:3000` | `healthcare-monitoring-overview` and `kafka-flink-service-health` dashboards |
| MLflow | `localhost:5000` | Agent traces and evaluation runs |
| Conduktor | `localhost:8085` | Topics, consumer lag, messages |

Agent metrics:

- `agent_service_http_request_duration_seconds` — request latency; the Grafana panel "RAG Query Latency (p50/p95)" uses it
- `agent_service_tool_execution_duration_seconds` and `agent_service_tool_execution_total` — MCP tool latency and outcomes

Alerts in `infra/observability/prometheus-alerts.yml`:

| Alert | Meaning | First step |
| --- | --- | --- |
| `Neo4jProbeDown` | Neo4j HTTP is unreachable | `docker logs healthcare-neo4j` |
| `Neo4jProbeLatencyHigh` | Neo4j responds slowly | Check heap and long-running queries |
| `QdrantTargetDown` | Qdrant metrics scrape fails | `docker logs healthcare-qdrant` |
| `KafkaProbeDown` | Broker TCP probe fails | `docker logs infra-kafka` |
| `FlinkJobManagerProbeDown` | Flink JobManager is unreachable | `docker logs healthcare-flink-jobmanager` |

MLflow tracing is on when `MLFLOW_TRACKING_URI` is set; `MLFLOW_EXPERIMENT_NAME` selects the experiment. Use `trace_id` from a response to find the run.

The DLQ topic `healthcare.dlq.events` is provisioned but nothing writes to it yet.

## 6. Flink operations

```bash
curl -s localhost:8082/jobs/overview                     # list jobs
curl -s localhost:8082/jobs/<job-id>/exceptions          # last failure
curl -s -X PATCH "localhost:8082/jobs/<job-id>?mode=cancel"
docker logs healthcare-flink-app --tail=200
```

The healthcare job is `HealthcareGraphRagPyFlinkJob`. Use port 8083 and the `supplychain-` containers for supply chain. To redeploy a job, cancel it and run `docker compose -p healthcare -f infra/compose/docker-compose.healthcare.yml up -d --force-recreate flink-app` (or `sc-flink-app` in the supply-chain project).

## 7. Embedding provider switch and re-index

Ingest (Flink) and query (agent) must use the same embedding model and dimension. See [04 — Data Platform](04_data_platform.md#embeddings).

| Setting | Dev | Production |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `local` (`all-MiniLM-L6-v2`) | `databricks` |
| `DATABRICKS_EMBEDDING_ENDPOINT` | — | `databricks-gte-large-en` |
| `EMBEDDING_DIM` | 384 | 1024 |
| `EMBEDDING_REQUIRE_MODEL` | `true` (compose default) | `true`, so startup fails instead of falling back to hashed vectors |

After any change to these settings, re-index:

1. Delete both collections:

   ```bash
   curl -s -X DELETE localhost:6333/collections/healthcare_events
   curl -s -X DELETE localhost:6335/collections/supplychain_events
   ```

2. Force-recreate `flink-app` and `agent-service` in the healthcare project, and `sc-flink-app` and `sc-agent-service` in the supply-chain project.
3. Let the producers replay events, or restart them.
4. On Kubernetes, set identical `EMBEDDING_*` values in the agent chart `secrets` and the Flink chart `secretEnv`.

| Symptom | Cause | Fix |
| --- | --- | --- |
| Qdrant `wrong vector dimension` | Collection was created with the other provider | Re-index |
| Relevant evidence missing | Ingest and query use different models | Align `EMBEDDING_*` and re-index |
| Startup fails with `EMBEDDING_REQUIRE_MODEL` | Model could not load | Check the image includes the model, or the Databricks endpoint and token |
| Databricks `401`/`403` | Token missing or lacks endpoint access | Fix the secret and the serving-endpoint permissions |

## 8. Sessions and human review

- Multi-turn memory is keyed by `session_id`. The default store is in-process (`SESSION_STORE_BACKEND=memory`), so sessions are lost on restart and are not shared between replicas. Use `SESSION_STORE_BACKEND=redis` with `REDIS_URL` for shared sessions. `SESSION_TTL_SECONDS` defaults to 3600 and at most 20 turns are kept.
- Human review is off unless `HITL_ENABLED=true`. Paused runs return `status: "pending_review"` and a `thread_id`. Resume them with:

  ```bash
  curl -s -X POST localhost:8000/query/resume \
    -H 'Content-Type: application/json' \
    -d '{"thread_id":"<thread-id>","decision":"approve","note":"checked"}'
  ```

- Configure `LANGGRAPH_CHECKPOINT_POSTGRES_URI` for shared, restart-safe LangGraph checkpoints. Set `LANGGRAPH_CHECKPOINT_REQUIRED=true` in production so startup fails instead of silently falling back to process-local memory. `HITL_MAX_PENDING` (default 1000) caps open reviews.

## 9. Kubernetes and Helm

The umbrella chart is `infra/helm` with sub-charts under `infra/helm/charts`. Dev uses namespace `healthcare-ai-dev` (release `healthcare-dev`); production uses `healthcare-ai` (release `healthcare`). See [03 — Platform Blueprint](03_platform_blueprint.md#3-kubernetes-with-helm).

| Task | Command |
| --- | --- |
| Deploy to minikube | `make helm-dev` (runs `infra/environments/dev/setup-minikube.sh`) |
| Port-forward services | `make minikube-ports`; stop with `make minikube-ports-stop` |
| Tear down dev | `make minikube-down` |
| Lint and render | `make helm-lint`, `make helm-prd` (dry-run only) |
| Pull the model in-cluster | `kubectl -n healthcare-ai-dev exec deploy/ollama -- ollama pull llama3.1` |

Production deployment requires:

- An EKS cluster and AWS role with permissions to update kubeconfig and deploy into `healthcare-ai`.
- Reachable external Qdrant and Neo4j services.
- GitHub Actions variable `DATABRICKS_HOST`.
- GitHub Actions secrets `DATABRICKS_TOKEN`, `NEO4J_PASSWORD`, and any configured LLM credentials.
- A Kubernetes Secret named `databricks-credentials` with key `token` for Flink.

The production workflow creates or updates the Databricks Secret, injects the Databricks host into both agent and Flink workloads, and waits for agent, web, and Flink rollouts. Use the same `EMBEDDING_PROVIDER=databricks`, `DATABRICKS_EMBEDDING_ENDPOINT=databricks-gte-large-en`, and `EMBEDDING_DIM=1024` for ingestion and query. Re-index Qdrant before switching from local 384-dimensional vectors.

For a manual deployment, supply secrets from your secret store; never commit them:

```bash
kubectl create namespace healthcare-ai --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic databricks-credentials \
  -n healthcare-ai \
  --from-literal=token="$DATABRICKS_TOKEN" \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install healthcare infra/helm \
  -f infra/helm/values-production.yaml \
  -n healthcare-ai --create-namespace \
  --set agent-service.config.DATABRICKS_HOST="$DATABRICKS_HOST" \
  --set agent-service.secrets.NEO4J_PASSWORD="$NEO4J_PASSWORD" \
  --set agent-service.secrets.ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  --set flink.config.DATABRICKS_HOST="$DATABRICKS_HOST" \
  --wait --timeout 5m

kubectl rollout status deployment/agent-service -n healthcare-ai --timeout=300s
kubectl rollout status deployment/provider-web -n healthcare-ai --timeout=300s
kubectl rollout status deployment/flink-jobmanager -n healthcare-ai --timeout=300s
kubectl rollout status deployment/flink-taskmanager -n healthcare-ai --timeout=300s
helm rollback healthcare <revision> -n healthcare-ai
```

Checks:

```bash
kubectl -n healthcare-ai-dev get pods
kubectl -n healthcare-ai-dev logs deploy/agent-service --tail=50
kubectl -n healthcare-ai-dev exec deploy/agent-service -- curl -s localhost:8000/health
```

## 10. Troubleshooting

### Compose stack

| Symptom | Cause | Fix |
| --- | --- | --- |
| "Found orphan containers" | Old services from earlier layouts | `make down` (uses `--remove-orphans`) |
| Agent `503` | Neo4j or Qdrant not ready | Wait for health checks; check `make ps` |
| LLM calls fail on first start | Ollama model not pulled | `make pull-model` |
| Network `graphrag-net` not found | Domain started without infra | `make up` or `make up-hc` |

### Flink

| Symptom | Cause | Fix |
| --- | --- | --- |
| Old demo job still running | Stale job from an earlier deploy | Cancel it (section 6) and recreate `flink-app` |
| `python: not found` in the task manager | PyFlink cannot find Python | The image symlinks `/usr/bin/python`; check `python.executable` in the Flink config |
| `ClassNotFoundException` for the Kafka connector | Connector jars missing from `/opt/flink/lib` | Rebuild the Flink image with `--no-cache` |
| Job restarts in a loop | Sink or deserialisation error | Read `/jobs/<id>/exceptions` |

### LLM providers

| Symptom | Cause | Fix |
| --- | --- | --- |
| Databricks `404` | Wrong serving endpoint name | Fix `LLM_MODEL` / the endpoint name |
| Databricks `400` on `temperature` | Model rejects the parameter | Retried automatically without it |
| Answers cut off | Token limit too low | Raise `LLM_MAX_TOKENS` (compose sets 4096) and `LLM_TIMEOUT_SECONDS` |
| Bedrock `AccessDenied` | IAM role lacks `bedrock:InvokeModel` | Fix the role or region |
| `ANTHROPIC_API_KEY not set` | Secret not injected | `kubectl -n healthcare-ai get secret agent-service-secrets` |
| Slow answers on CPU | Local inference | Expected; use a smaller model or a hosted provider |

### Minikube

| Symptom | Cause | Fix |
| --- | --- | --- |
| `K8S_APISERVER_MISSING` | Stale cluster state | `minikube delete && make helm-dev` |
| Pods crash on env var collisions | Kubernetes service links | Charts set `enableServiceLinks: false`; keep it |
| Ollama `OOMKilled` | Not enough memory | `MINIKUBE_MEMORY=20480 make helm-dev` |
| `ImagePullBackOff` | Image built outside minikube's Docker | `eval $(minikube docker-env)` and rebuild; the setup script does this |
| Flink task manager cannot register | RPC port blocked | Check port 6124 in the network policy |
| Port-forward drops | `kubectl` limit on long connections | Re-run `make minikube-ports` |

### Minikube credentials, reboot and troubleshooting

- Put real credentials in the gitignored `infra/helm/values-dev.local.yaml` (`agent-service.secrets.DATABRICKS_TOKEN`). `setup-minikube.sh` applies it automatically; for manual upgrades pass `-f infra/helm/values-dev.yaml -f infra/helm/values-dev.local.yaml`. Never commit tokens (GitHub push protection will block them).
- Reboot: `minikube stop && minikube start`, wait for pods to be Ready, then `make minikube-ports`.

| Symptom | Cause | Fix |
|---|---|---|
| localhost:5000 down, mlflow `OOMKilled` | Dev memory too low / persistence | Dev values disable persistence and raise limits; re-run helm upgrade |
| Agent UI "Request timed out after 120s" | mlflow down (agent retries) or `Permission denied: /mlflow` | Ensure mlflow runs with `--serve-artifacts`; restart agent-service |
| "LLM error: unable to reach Databricks AI Gateway" | `DATABRICKS_HOST/TOKEN` still `change_me` | Fill `values-dev.local.yaml`, helm upgrade, restart agent-service |

### Conduktor

| Symptom | Cause | Fix |
| --- | --- | --- |
| Messages show as bytes | Default deserializer | Choose Avro (Schema Registry) with `http://schema-registry:8081` |
| Payload looks escaped | `payload_json` is a JSON string inside Avro | Expected; parse it client-side |

## 11. Escalation

Collect before escalating:

- `make ps` output and the failing container's logs (`docker logs <container> --tail=500`)
- `/health` and `/mcp/health` responses
- the `trace_id` of the failing request, and the MLflow trace for it
- Flink `/jobs/<id>/exceptions` for pipeline issues
- the active `LLM_*` and `EMBEDDING_*` settings, without secrets

Raise `LANGGRAPH_MAX_ITERATIONS` (default 3) only to diagnose low-confidence loops, and revert afterwards.

## Related

- [03 — Platform Blueprint](03_platform_blueprint.md) — deployment topology and configuration
- [04 — Data Platform](04_data_platform.md) — topics, Flink jobs, stores
- [05 — AI Agents](05_ai_agents.md) — API and configuration reference
- [06 — Quality Assurance](06_quality_assurance.md) — tests and evaluation gates
- [07 — CI/CD Automation](07_cicd_automation.md) — pipelines and local equivalents
