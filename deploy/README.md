# Deployment

This directory contains all deployment configurations for the Healthcare AI GraphRAG platform.

## Directory Structure

```
deploy/
├── helm/                       Helm umbrella chart (Kubernetes deployment)
│   ├── Chart.yaml              Umbrella chart with sub-chart dependencies
│   ├── values.yaml             Default values
│   ├── values-dev.yaml         Dev overrides (single replica, Ollama, full infra)
│   ├── values-production.yaml  Production overrides (multi-replica, OpenAI+Anthropic)
│   ├── templates/              Namespace, NetworkPolicy, helpers
│   └── charts/
│       ├── rag-api/            AI agents with embedded MCP
│       ├── provider-web/       Frontend UI
│       ├── flink/              Flink cluster (JobManager + TaskManager + job)
│       ├── mlflow/             Tracing and evaluation server
│       ├── kafka/              Confluent Kafka (Zookeeper + broker + Schema Registry)
│       ├── neo4j/              Neo4j graph database
│       ├── qdrant/             Qdrant vector database
│       └── ollama/             Local LLM inference server
├── dev/                        Local development (Docker Compose)
│   ├── docker-compose.yml
│   ├── docker-compose.monitoring.yml
│   ├── rag-api.env
│   ├── monitoring/
│   └── setup-minikube.sh
└── production/                 Production Docker Compose variant
    ├── docker-compose.ai.yml
    ├── docker-compose.monitoring.yml
    ├── monitoring/
    └── rag-api.env.example
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
| Ollama (LLM) | Helm sub-chart | Not deployed (uses OpenAI/Anthropic APIs) |

## LLM Provider Routing

| Environment | Primary Provider | Fallback Provider |
|-------------|-----------------|-------------------|
| Dev / Local | Ollama (`llama3.1`) | none |
| Production | OpenAI (`gpt-4.1-mini`) | Anthropic (`claude-sonnet-4-20250514`) |

The `LLM_FALLBACK_PROVIDER` env var enables automatic failover — if the primary returns an error, the request is retried against the fallback.

---

## Local Development

### Option A: Docker Compose (recommended for quick start)

```bash
cd deploy/dev
docker compose up -d                          # rag-api, neo4j, qdrant, ollama, provider-web
docker compose -f docker-compose.monitoring.yml up -d  # prometheus, grafana, blackbox
```

Services on localhost:

| Service | Port | URL |
|---------|------|-----|
| RAG API | 8000 | `http://localhost:8000` |
| Provider Web | 8088 | `http://localhost:8088` |
| Neo4j Browser | 7474 | `http://localhost:7474` |
| Qdrant | 6333 | `http://localhost:6333` |
| Ollama | 11434 | `http://localhost:11434` |
| Prometheus | 9090 | `http://localhost:9090` |
| Grafana | 3000 | `http://localhost:3000` |

Tear down:

```bash
docker compose down -v
docker compose -f docker-compose.monitoring.yml down -v
```

### Option B: Helm on Minikube

```bash
make helm-dev    # one-command bootstrap
# Or manually:
minikube start --cpus=4 --memory=8192
helm install healthcare-dev deploy/helm -f deploy/helm/values-dev.yaml -n healthcare-ai-dev --create-namespace
```

Services exposed via NodePort:

| Service | NodePort | URL |
|---------|----------|-----|
| RAG API | 30800 | `http://$(minikube ip):30800` |

Dev differences from production:
- All deployments scaled to 1 replica
- LLM provider: local Ollama (no external API keys needed)
- Kafka, Neo4j, Qdrant, Ollama deployed in-cluster
- `RAG_API_ALLOW_ROLE_HEADER: true` for testing
- No NetworkPolicy enforcement
- No HPA (autoscaling disabled)

Tear down:

```bash
make helm-dev-down
minikube delete  # full reset
```

---

## Production

### Deploy (Helm)

```bash
helm install healthcare deploy/helm \
  -f deploy/helm/values-production.yaml \
  -n healthcare-ai --create-namespace \
  --set rag-api.secrets.NEO4J_PASSWORD=<value> \
  --set rag-api.secrets.OPENAI_API_KEY=<value> \
  --set rag-api.secrets.ANTHROPIC_API_KEY=<value>
```

Upgrade:

```bash
helm upgrade healthcare deploy/helm -f deploy/helm/values-production.yaml -n healthcare-ai
```

### Platform Controls

- NetworkPolicy: default deny ingress for namespace (enabled in production values)
- HPA: `rag-api` (2–6), `provider-web` (2–5); requires metrics-server

### Deploy (Docker Compose)

```bash
cp deploy/production/rag-api.env.example deploy/production/rag-api.env
# Edit rag-api.env with real credentials

docker compose -f deploy/production/docker-compose.ai.yml up -d
docker compose -f deploy/production/docker-compose.monitoring.yml up -d
```

---

## Secrets and Credentials

- Replace all `change_me` values before deployment.
- Inject API keys and passwords from a secret manager or sealed secret workflow.
- Never commit populated `.env` files or rendered secret manifests.
- Required secrets (production): `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- Dev uses hardcoded defaults (no external API keys needed).

---

## Configuration Guidelines

| Area | Guidance |
|------|----------|
| Images | Pin to immutable tags or digests; promote same artifact across envs |
| Namespaces | Dedicated per environment with scoped RBAC |
| Networking | TLS at ingress; restrict with NetworkPolicy/security groups |
| Origins | Set `RAG_API_ALLOW_ORIGINS` to explicit trusted origins |
| Scaling | Size rag-api and provider-web independently; validate HPA thresholds |
| MLflow | PostgreSQL backend + object store for production (not SQLite) |
| Observability | Ship logs to centralized store; alert on health/latency/errors |

---

## Endpoint Checks

| Endpoint | Path |
|----------|------|
| RAG API health | `/health` |
| Embedded MCP diagnostics | `/mcp/health` |
| Embedded MCP protocol | `/mcp` |
| Provider web | `/` |

---

## GitHub Actions CD

Workflow: `.github/workflows/deploy-ai-prd.yml`

- Triggers on push to `prd` branch or `workflow_dispatch`
- Deploys to AWS EKS

Required secrets: `NEO4J_PASSWORD`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
Required variables: `AWS_ROLE_TO_ASSUME`, `AWS_REGION`, `EKS_CLUSTER_NAME`
