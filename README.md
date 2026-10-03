# Agentic AI Healthcare + Supply Chain GraphRAG

A local-first multi-domain Python workspace for building and running GraphRAG-style AI systems across healthcare and supply-chain domains. The repository is organized as a uv-managed monorepo with shared runtime packages and domain-specific agent services, streaming pipelines, knowledge assets, and web apps.

The implementation is broader than the older single-platform README narrative: the codebase is currently structured around shared infrastructure plus two active domains.

- Healthcare
- Supply chain

with Docker Compose overlays, a Makefile-driven developer workflow, and domain-specific data pipelines and agent services.

## What the repo contains

The current project structure is a real workspace, not a single app package:

- `packages/agent-core` — shared orchestration/runtime utilities
- `packages/knowledge-core` — shared knowledge and graph-related abstractions
- `domains/healthcare/` — healthcare agent service, data pipelines, knowledge seeds, scripts, web app
- `domains/supply-chain/` — supply-chain agent service, data pipelines, knowledge seeds, scripts, web app
- `infra/compose/` — shared infra stack and domain overlays
- `infra/helm/` — Helm deployment assets
- `scripts/` — validation and workflow helpers
- `docs/` — architecture, operations, and domain documentation

## Architecture summary

The runtime model is organized into tiers:

- Shared infrastructure: Kafka, Schema Registry, Ollama, Prometheus, Grafana, MLflow, LocalStack, and supporting services
- Healthcare domain overlay: Neo4j, Qdrant, Kafka topics, Flink job, producer, agent service, webapp
- Supply-chain domain overlay: separate Neo4j, Qdrant, Kafka topics, producer, Flink job, and agent service
- Shared Python packages used by both domains

This is a local development and experimentation platform with a multi-domain GraphRAG stack rather than a single product service.

## Core stack

The implementation currently reflects these technologies:

- Python + uv workspace management
- FastAPI + Uvicorn
- LangGraph (checkpointer-backed human-in-the-loop review)
- Neo4j for graph memory and ontology data
- Qdrant for vector retrieval
- Kafka + Schema Registry + Flink for streaming ingestion and processing
- MLflow + Grafana + Prometheus for observability
- Docker Compose and Helm for local and deployment workflows
- Pydantic and typed Python services across the shared packages and domain services

## Local developer workflow

The project uses a Makefile as the main entry point for local orchestration.

### Bootstrap and lifecycle

```bash
make up          # Start shared infra + healthcare + supply-chain
make up-hc       # Start infra + healthcare domain
make up-sc       # Start infra + supply-chain domain
make down        # Stop everything and remove the network
make ps          # Show running containers
make logs        # Tail healthcare logs
make logs-sc     # Tail supply-chain logs
```

### Domain and service access

```bash
make api-hc      # Health check for healthcare API
make api-sc      # Health check for supply-chain API
make query-hc    # Run healthcare query examples
make query-sc    # Run supply-chain query examples
make flink-hc    # Healthcare Flink overview
make flink-sc    # Supply-chain Flink overview
make topics      # List Kafka topics
make mlflow      # MLflow health check
```

### Validation and tests

```bash
make validate            # Cross-domain stack validation
make validate-docs       # Markdown validation
make validate-skills     # Agent skill package sync checks
make validate-ontology   # Ontology validation for both domains
make test-unit           # Fast unit tests for agent-core + domains
make test-integration    # Integration tests (no live services)
make test-evals          # Offline evaluation suites
make lint                # Ruff linting across packages and domains
```

### Healthcare web UI

```bash
make web-hc-dev      # Vite dev server for healthcare UI
make web-hc-test     # Typecheck and unit tests for healthcare web app
make web-hc-build    # Production build for healthcare web app
```

## Service endpoints

The current local stack exposes the following ports:

| Service | URL |
|---------|-----|
| Healthcare agent service | http://localhost:8000 |
| Supply-chain agent service | http://localhost:8001 |
| Healthcare web app | http://localhost:8088 |
| Supply-chain web app | http://localhost:8089 |
| Healthcare Neo4j Browser | http://localhost:7474 |
| Supply-chain Neo4j Browser | http://localhost:7475 |
| Healthcare Qdrant | http://localhost:6333 |
| Supply-chain Qdrant | http://localhost:6335 |
| Healthcare Flink dashboard | http://localhost:8082 |
| Supply-chain Flink dashboard | http://localhost:8083 |
| Grafana | http://localhost:3000 |
| MLflow | http://localhost:5000 |

## Default credentials

| Service | Username | Password |
|---------|----------|----------|
| Healthcare Neo4j | neo4j | healthcare123 |
| Supply-chain Neo4j | neo4j | supplychain123 |
| Grafana | admin | admin123 |

## Repository layout

```text
.
├── Makefile
├── pyproject.toml
├── uv.lock
├── docs/                          # Architecture, operations, and domain design docs
├── domains/
│   ├── healthcare/
│   │   ├── agent-service/
│   │   ├── data-pipelines/
│   │   ├── knowledge/
│   │   ├── scripts/
│   │   └── webapp/
│   └── supply-chain/
│       ├── agent-service/
│       ├── data-pipelines/
│       ├── knowledge/
│       ├── scripts/
│       └── webapp/
├── packages/
│   ├── agent-core/
│   └── knowledge-core/
├── infra/
│   ├── compose/
│   ├── helm/
│   ├── environments/
│   ├── observability/
│   ├── images/
│   └── web/
├── scripts/
├── deploy/
├── container/
├── volume/
└── README.md
```

## Documentation

See the project docs for the deeper architecture and operating model:

- [docs/](docs/)
- [docs/01_business_requirements.md](docs/01_business_requirements.md)
- [docs/02_architecture.md](docs/02_architecture.md)
- [docs/04_data_platform.md](docs/04_data_platform.md)
- [docs/05_ai_agents.md](docs/05_ai_agents.md)
- [docs/08_operation_runbook.md](docs/08_operation_runbook.md)
- [docs/adrs/README.md](docs/adrs/README.md)

## Safety note

This repository contains synthetic or demo-oriented data and local development assets. It is not a clinical system, not a regulated medical device, and any AI-generated output should be treated as advisory only and validated independently before use in operational or clinical settings.
