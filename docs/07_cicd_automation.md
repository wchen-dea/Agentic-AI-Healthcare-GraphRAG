# CI/CD and Deployment Automation

This document covers deployment configurations and CI/CD automation for the Healthcare AI GraphRAG platform.

## Directory Structure

```
infra/
├── compose/                    Local Docker Compose (infra + per-domain stacks)
├── environments/
│   ├── dev/
│   │   └── setup-minikube.sh   Minikube bootstrap (local Compose lives in infra/compose/)
│   └── production/             Production Docker Compose variant
│       ├── docker-compose.ai.yml
│       ├── docker-compose.monitoring.yml
│       ├── monitoring/
│       └── agent-service.env.example
├── helm/                       Helm umbrella chart (Kubernetes deployment)
│   ├── Chart.yaml              Umbrella chart with sub-chart dependencies
│   ├── values.yaml             Default values
│   ├── values-dev.yaml         Dev overrides (single replica, Databricks LLM, full infra)
│   ├── values-production.yaml  Production overrides (multi-replica, Bedrock+fallback)
│   ├── templates/              Namespace, NetworkPolicy, helpers
│   └── charts/
│       ├── agent-service/      Healthcare AI agents with embedded MCP
│       ├── provider-web/       Frontend UI
│       ├── flink/              Flink cluster (JobManager + TaskManager + job)
│       ├── mlflow/             Tracing and evaluation server
│       ├── kafka/              Confluent Kafka (Zookeeper + broker + Schema Registry)
│       ├── conduktor/          Kafka console
│       ├── producer/           Synthetic event producer
│       ├── neo4j/              Neo4j graph database
│       ├── qdrant/             Qdrant vector database
│       └── ollama/             Local LLM inference server (optional provider)
├── images/flink-cluster/       Legacy shared Flink image (unused; Flink runs per-domain)
├── observability/              Prometheus, alerts, blackbox, Grafana config
└── web/nginx.conf              Frontend reverse-proxy config
```

## In-Scope Components

- Healthcare agents service (embedded FastMCP at `/mcp`)
- Provider web UI
- Flink cluster (JobManager + TaskManager)
- Flink job submitter (healthcare domain)
- MLflow tracing server
- Monitoring stack (Prometheus, Grafana, Blackbox Exporter)

### Infrastructure (deployed in dev, external in production)

| Component | Dev (in-cluster) | Production |
|-----------|-----------------|------------|
| Kafka + Schema Registry | Helm sub-chart | Managed Confluent platform |
| Neo4j | Helm sub-chart | Managed service |
| Qdrant | Helm sub-chart | Managed service |
| Ollama (LLM) | Helm sub-chart | Not deployed (uses AWS Bedrock) |

## LLM Provider Routing

| Environment | Primary Provider | Fallback Provider |
|-------------|-----------------|-------------------|
| Dev / Local | Ollama (`llama3.1`) | none |
| Production | Bedrock (`anthropic.claude-3-5-haiku-20241022-v1:0`) | Anthropic (`claude-sonnet-4-20250514`) |

The `LLM_FALLBACK_PROVIDER` env var enables automatic failover — if the primary returns an error, the request is retried against the fallback.

---

## Local Development

### Option A: Docker Compose (recommended for quick start)

Uses the canonical stacks in `infra/compose/`, configured by the repo-root `.env` (copy `.env.example`).

```bash
make up-hc    # infra stack (kafka, ollama, prometheus, grafana, blackbox, ...) + healthcare stack
# Equivalent:
# docker compose -f infra/compose/docker-compose.infra.yml -p infra up -d
# docker compose -f infra/compose/docker-compose.healthcare.yml -p healthcare up -d
```

Services on localhost:

| Service | Port | URL |
|---------|------|-----|
| Agent API | 8000 | `http://localhost:8000` |
| Provider Web | 8088 | `http://localhost:8088` |
| Neo4j Browser | 7474 | `http://localhost:7474` |
| Qdrant | 6333 | `http://localhost:6333` |
| Flink UI | 8082 | `http://localhost:8082` |
| Ollama | 11434 | `http://localhost:11434` |
| Prometheus | 9090 | `http://localhost:9090` |
| Grafana | 3000 | `http://localhost:3000` |

Tear down:

```bash
make down
```

### Option B: Helm on Minikube

```bash
make helm-dev    # one-command bootstrap
# Or manually:
minikube start --cpus=4 --memory=8192
helm install healthcare-dev infra/helm -f infra/helm/values-dev.yaml -n healthcare-ai-dev --create-namespace
```

Services exposed via NodePort:

| Service | NodePort | URL |
|---------|----------|-----|
| Agent API | 30800 | `http://$(minikube ip):30800` |

On macOS with Docker driver, NodePorts aren't directly accessible. Use port-forwards:

```bash
make helm-ports       # start all port-forwards
make helm-ports-stop  # kill them
```

| Service | Port-forward URL |
|---------|-----------------|
| Agent API | `http://localhost:8000` |
| Web UI | `http://localhost:8088` |
| Neo4j | `http://localhost:7474` |
| Qdrant | `http://localhost:6333/dashboard` |
| Conduktor | `http://localhost:9080` |

Dev differences from production:

- All deployments scaled to 1 replica
- LLM provider: local Ollama (no external API keys needed)
- Kafka, Neo4j, Qdrant, Ollama deployed in-cluster
- `AGENT_ALLOW_ROLE_HEADER: true` for testing
- No NetworkPolicy enforcement
- No HPA (autoscaling disabled)
- Default model: `qwen2.5:1.5b` (fits in 16GB minikube)

Tear down:

```bash
make helm-dev-down
minikube delete  # full reset
```

---

## Production

### Deploy (Helm)

```bash
helm install healthcare infra/helm \
  -f infra/helm/values-production.yaml \
  -n healthcare-ai --create-namespace \
  --set agent-service.secrets.NEO4J_PASSWORD=<value> \
  --set agent-service.secrets.OPENAI_API_KEY=<value> \
  --set agent-service.secrets.ANTHROPIC_API_KEY=<value>
```

`OPENAI_API_KEY` is optional; set it only when using the OpenAI provider or fallback.

Upgrade:

```bash
helm upgrade healthcare infra/helm -f infra/helm/values-production.yaml -n healthcare-ai
```

### Platform Controls

- NetworkPolicy: default deny ingress for namespace (enabled in production values)
- HPA: `agent-service` (2–6), `provider-web` (2–5); requires metrics-server

### Deploy (Docker Compose)

```bash
cp infra/environments/production/agent-service.env.example infra/environments/production/agent-service.env
# Edit agent-service.env with real credentials

docker compose -f infra/environments/production/docker-compose.ai.yml up -d
docker compose -f infra/environments/production/docker-compose.monitoring.yml up -d
```

---

## Secrets and Credentials

- Replace all `change_me` values before deployment.
- Inject API keys and passwords from a secret manager or sealed secret workflow.
- Never commit populated `.env` files or rendered secret manifests.
- Required secrets (production): `NEO4J_PASSWORD`, `ANTHROPIC_API_KEY` (optional: `OPENAI_API_KEY`)
- Dev uses hardcoded defaults (no external API keys needed).

---

## Technology Version Matrix

| Technology | Version | Component |
|------------|---------|-----------|
| Python | 3.11 | All Python services |
| Java | 17 | Flink runtime |
| Apache Flink | 1.20.5 | Stream processing cluster |
| PyFlink | 1.20.5 | Python stream jobs |
| Flink Kafka Connector | 3.4.0 | Flink–Kafka integration |
| Confluent Kafka (Docker) | 7.9.0 | Kafka brokers, Zookeeper, Schema Registry |
| Confluent Kafka (Helm) | 7.6.0 | Kafka brokers (minikube) |
| Neo4j | 5.26.2 (Docker) / 5-community (Helm) | Knowledge graph |
| Qdrant | v1.12.1 | Vector store |
| Ollama | latest | Local LLM inference |
| FastAPI | 0.115.0 | Agent API framework |
| LangGraph | >=0.4.1 | Multi-agent orchestration |
| LangChain Core | >=0.3.0 | Agent framework |
| MCP SDK | 1.28.0 | Tool protocol |
| MLflow | v2.21.3 | Tracing and evaluation |
| Conduktor Console | 1.25.1 | Kafka management UI |
| sentence-transformers | 3.0.1 | Embedding model |
| neo4j (Python driver) | 5.24.0 | Graph client |
| qdrant-client | 1.11.3 | Vector client |
| confluent-kafka (Python) | 2.5.3 | Kafka producer |
| Prometheus | latest | Metrics collection |
| Grafana | latest | Dashboards |

---

## Configuration Guidelines

| Area | Guidance |
|------|----------|
| Images | Pin to immutable tags or digests; promote same artifact across envs |
| Namespaces | Dedicated per environment with scoped RBAC |
| Networking | TLS at ingress; restrict with NetworkPolicy/security groups |
| Origins | Set `AGENT_ALLOW_ORIGINS` to explicit trusted origins |
| Scaling | Size agent-service and provider-web independently; validate HPA thresholds |
| MLflow | PostgreSQL backend + object store for production (not SQLite) |
| Observability | Ship logs to centralized store; alert on health/latency/errors |

---

## Endpoint Checks

| Endpoint | Path |
|----------|------|
| Agent API health | `/health` |
| Embedded MCP diagnostics | `/mcp/health` |
| Embedded MCP protocol | `/mcp` |
| Provider web | `/` |

---

## GitHub Actions CD

Workflow: `.github/workflows/deploy-ai-prd.yml`

- Triggers on push to `prd` branch or `workflow_dispatch`
- Deploys to AWS EKS

Required secrets: `NEO4J_PASSWORD`, `ANTHROPIC_API_KEY` (optional: `OPENAI_API_KEY`)
Required variables: `AWS_ROLE_TO_ASSUME`, `AWS_REGION`, `EKS_CLUSTER_NAME`
