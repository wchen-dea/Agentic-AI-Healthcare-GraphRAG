# Production Deployment Bundle (AI Components Only)

This folder contains production deployment configuration for **AI app deliverables only**.

In-scope components from this project:

- `rag-api` (includes embedded FastMCP at `/mcp`)
- `provider-web`
- optional standalone `mcp-server` profile
- monitoring stack in a separate compose file

Out-of-scope components (managed independently):

- source data systems and upstream application environments
- Confluent Kafka platform (independently operated by IT operations)
- Apache Flink platform (independently deployed on AWS EKS/Kubernetes)

## Files

- `docker-compose.ai.yml`: AI runtime deployment (rag-api, provider-web, optional standalone MCP)
- `docker-compose.monitoring.yml`: monitoring deployment (Prometheus, Grafana, Blackbox Exporter)
- `k8s/`: Kubernetes-ready manifests for AI components (base + optional standalone MCP)
- `rag-api.env.example`: production environment template for rag-api
- `mcp-server.env.example`: standalone MCP profile environment template
- `monitoring/`: Prometheus and Blackbox config for probing AI endpoints

## Runtime Topology

- Preferred mode: embedded MCP in rag-api at `http://<rag-api-host>:8000/mcp`
- Optional mode: standalone MCP container at `http://<mcp-host>:8010/mcp` via profile `standalone-mcp`

## Quick Start

### Docker Compose Variant

1. Prepare env files:

```bash
cp rag-api.env.example rag-api.env
cp mcp-server.env.example mcp-server.env
```

1. Deploy AI runtime:

```bash
docker compose -f docker-compose.ai.yml up -d
```

1. Optional standalone MCP runtime:

```bash
docker compose -f docker-compose.ai.yml --profile standalone-mcp up -d
```

1. Deploy monitoring separately:

```bash
docker compose -f docker-compose.monitoring.yml up -d
```

### Kubernetes Variant

See [k8s/README.md](k8s/README.md) for base deployment (`rag-api` + `provider-web`) and optional standalone `mcp-server` manifests.

## Endpoint Checks

- RAG API health: `http://localhost:8000/health`
- Embedded MCP diagnostics: `http://localhost:8000/mcp/health`
- Embedded MCP protocol endpoint: `http://localhost:8000/mcp`
- Provider web: `http://localhost:8088`
- Standalone MCP protocol endpoint (optional): `http://localhost:8010/mcp`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
