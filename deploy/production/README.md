# Production Deployment Bundle (AI Components Only)

This folder contains production-oriented deployment configuration for **AI app deliverables only**.

Interpretation of "production-ready" in this repository:

- The root local Compose stack is a development and synthetic-demo environment.
- The assets in this folder are the production-ready part of the repository: environment templates, Compose variants, and Kubernetes manifests intended to be adapted to your production controls.
- These files are deployment starting points, not a claim that the repository's local defaults are production-hardened as delivered.

In-scope components from this project:

- Healthcare agents service (includes embedded FastMCP at `/mcp`)
- Provider web UI
- Flink cluster (shared JobManager + TaskManager)
- Flink job submitter (healthcare domain)
- MLflow tracing server
- Monitoring stack (Prometheus, Grafana, Blackbox Exporter)

Out-of-scope components (managed independently):

- Source data systems and upstream application environments
- Confluent Kafka platform (independently operated)
- Neo4j and Qdrant (independently deployed or managed service)

## Files

- `docker-compose.ai.yml`: AI runtime deployment (agents service, provider-web)
- `docker-compose.monitoring.yml`: monitoring deployment (Prometheus, Grafana, Blackbox Exporter)
- `k8s/`: Kubernetes manifests (agents, Flink cluster, MLflow, provider-web, network policies)
- `rag-api.env.example`: production environment template for the agents service
- `monitoring/`: Prometheus and Blackbox config for probing AI endpoints

## Runtime Topology

- Preferred mode: embedded MCP in rag-api at `http://<rag-api-host>:8000/mcp`

## Production Deployment Configuration Guidelines

Use the files in this folder as a deployment baseline and apply environment-specific controls before promoting to production.

### 1. Configuration Ownership

- Keep root-level local Compose files for development only.
- Treat `deploy/production/` assets as the only production deployment source in this repository.
- Maintain separate values per environment such as `stage` and `prod`; do not reuse one env file across environments.

### 2. Secrets And Credentials

- Replace all example values such as `change_me` before deployment.
- Inject API keys, database passwords, and tokens from a secret manager or sealed secret workflow.
- Do not commit populated `.env` files or rendered secret manifests back to source control.
- Rotate credentials on a defined schedule and after any exposure event.

### Production Secret Configuration Workflow

Use one of the following patterns depending on your deployment target.

#### Compose-based production bundle

1. Create runtime env file from the example:

```bash
cp rag-api.env.example rag-api.env
```

1. Populate secret-bearing values before deployment, especially:

- `NEO4J_PASSWORD`
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY`

1. Store the populated env file outside source control and distribute through your environment's secret handling process.

1. Deploy with the env file present on the target host:

```bash
docker compose -f docker-compose.ai.yml up -d
```

#### Kubernetes deployment bundle

1. Create secret manifest from the provided example:

```bash
cp k8s/base/rag-api-secret.example.yaml k8s/base/rag-api-secret.yaml
```

1. Replace example values with environment-specific secrets.

1. Prefer your platform secret workflow if available, such as External Secrets, Sealed Secrets, or another managed secret controller.

1. Apply secrets separately from the base manifests:

```bash
kubectl apply -f k8s/base/rag-api-secret.yaml
```

### 3. Image And Release Management

- Pin deployable images to immutable version tags or digests.
- Promote the same tested image artifact across environments instead of rebuilding per environment.
- Record the application version, image digest, and config revision together for each release.

### 4. Networking And Exposure

- Expose only the required public endpoints, typically `provider-web` and the intended `rag-api` ingress path.
- Keep administrative surfaces behind explicit access controls.
- Terminate TLS at the ingress or load balancer layer and enforce HTTPS for external traffic.
- Restrict ingress and egress with platform firewall, security group, or network policy controls.

### 5. Runtime Configuration

- Set `RAG_API_ALLOW_ORIGINS` to explicit trusted origins; never leave wildcard browser origins in production.
- Set `RAG_API_TOOL_POLICY_PATH` and caller-role policy values explicitly per environment.
- Bound LLM latency and output with `LLM_TIMEOUT_SECONDS`, `LLM_MAX_TOKENS`, and related provider limits.
- Current `rag-api` implementation is local-Ollama-first; if you require managed providers, implement and validate the provider adapter path before relying on `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` at runtime.

### 6. Scaling And Availability

- Run more than one `rag-api` replica behind a load balancer for production traffic.
- Size `provider-web` and `rag-api` independently based on observed traffic patterns.
- Validate autoscaling thresholds against real CPU, memory, and latency behavior before enabling them broadly.
- Ensure upstream dependencies such as Kafka, Flink, vector storage, graph storage, and LLM providers meet the same availability target expected from the AI app tier.

### 7. Observability And Audit

- Ship application logs, audit logs, and platform logs to a centralized log store.
- Keep Prometheus and Grafana configs aligned with the deployed topology and ingress names.
- When MLflow is deployed for agent tracing, configure `MLFLOW_TRACKING_URI` on the rag-api service. Use a persistent backend store (PostgreSQL recommended over SQLite for production). Set artifact storage to a shared volume or object store.
- Alert on health failures, elevated latency, error rate, and audit anomalies rather than relying on manual endpoint checks.
- Retain audit data according to your environment's compliance and investigation requirements.
- MLflow traces and audit log `trace_id` values can be correlated for end-to-end query observability.", "oldString": "### 7. Observability And Audit\n\n- Ship application logs, audit logs, and platform logs to a centralized log store.\n- Keep Prometheus and Grafana configs aligned with the deployed topology and ingress names.\n- Alert on health failures, elevated latency, error rate, and audit anomalies rather than relying on manual endpoint checks.\n- Retain audit data according to your environment's compliance and investigation requirements.

### 8. Promotion And Change Control

- Validate config changes in a lower environment before production rollout.
- Use rolling or canary deployment strategies when the platform supports them.
- Keep rollback instructions for image, config, and secret changes.
- Re-run smoke checks after each rollout, especially `/health`, `/mcp/health`, provider UI access, and any environment-specific synthetic queries.

## Quick Start

These steps describe how to use the production deployment bundle assets. They do not change the fact that root-level local config in this repository is development-only.

### Docker Compose Variant

1. Prepare env files:

```bash
cp rag-api.env.example rag-api.env
```

1. Deploy AI runtime:

```bash
docker compose -f docker-compose.ai.yml up -d
```

1. Deploy monitoring separately:

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

### Kubernetes Variant

See [k8s/README.md](k8s/README.md) for full deployment (agents, Flink cluster, MLflow, provider-web).

## Endpoint Checks

- RAG API health: `http://localhost:8000/health`
- Embedded MCP diagnostics: `http://localhost:8000/mcp/health`
- Embedded MCP protocol endpoint: `http://localhost:8000/mcp`
- Provider web: `http://localhost:8088`
- Standalone MCP protocol endpoint (optional): `http://localhost:8010/mcp`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## GitHub Actions CD For `prd`

This repository includes a production CD workflow at `.github/workflows/deploy-ai-prd.yml`.

Behavior:

- triggers on pushes to the `prd` branch
- can also be started manually with `workflow_dispatch`
- deploys the AI app Kubernetes base manifests to AWS EKS

Required GitHub Actions secrets:

- `NEO4J_PASSWORD`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Required GitHub Actions variables:

- `AWS_ROLE_TO_ASSUME`
- `AWS_REGION`
- `EKS_CLUSTER_NAME`

The workflow applies the `healthcare-ai` namespace, creates or updates the `rag-api-secrets` Kubernetes secret, applies `deploy/production/k8s/base`, and waits for the `rag-api` and `provider-web` rollouts to complete.
