# Agentic AI Healthcare Platform — Streaming GraphRAG with Multi-Agent Orchestration

End-to-end clinical decision-support system that streams healthcare events through Kafka and Flink, persists them as vector embeddings (Qdrant) and a knowledge graph (Neo4j), and answers clinical questions through multi-agent reasoning with domain-routed retrieval, guardrails, and structured output.

Runs fully local on Ollama, scales to AWS Bedrock in production with complexity-based model routing and optional fallback providers.

## Tech Stack

| Layer | Technologies |
|-------|-------------|
| Streaming | Apache Kafka, Schema Registry, Apache Flink (PyFlink) |
| Data Stores | Qdrant (vector), Neo4j (graph) |
| AI & API | FastAPI + embedded MCP, LangGraph, LangChain |
| LLM | Ollama (dev), AWS Bedrock (prod, with fallback) |
| Frontend | Nginx-served provider web app |
| Observability | Prometheus, Grafana, MLflow Tracing, LangSmith |
| Deployment | Helm, Docker Compose, minikube |

## Innovation Highlights

- **Streaming intelligence** — Kafka + PyFlink; events queryable in seconds
- **Hybrid GraphRAG** — Qdrant vectors + Neo4j relationships in every answer
- **Multi-agent orchestration** — LangGraph with 8 specialist nodes and confidence-gated re-retrieval
- **Pharmacovigilance knowledge graph** — 41 interaction + 46 reaction + 23 contraindication edges
- **Explainability** — vector_context, graph_context, retrieval_plan, confidence returned with every answer
- **10 MCP tools** — role-based auth, audit hashing, response budgets
- **MLflow evaluation** — 6 healthcare scorers, cross-mode comparison
- **Multi-domain** — Healthcare + Supply Chain on shared infrastructure
- **Local-first** — full stack on a laptop, zero API fees

## Quick Start

```bash
make up          # Start all services (infra + healthcare + supply-chain)
make ps          # Verify containers
make query-hc    # Run healthcare query examples
make query-sc    # Run supply-chain query examples
```

Minikube (Kubernetes):

```bash
make helm-dev    # Deploy full stack to minikube
make helm-ports  # Start port-forwards
```

## Service Endpoints (Docker Compose)

| Service | URL |
|---------|-----|
| Healthcare RAG API | http://localhost:8000 |
| Healthcare Web UI | http://localhost:8088 |
| Supply-chain RAG API | http://localhost:8001 |
| Neo4j Browser (HC) | http://localhost:7474 |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Flink Dashboard | http://localhost:8082 |
| Grafana | http://localhost:3000 |
| MLflow | http://localhost:5000 |

## Default Credentials

| Service | User | Password |
|---------|------|----------|
| Neo4j (healthcare) | neo4j | healthcare123 |
| Neo4j (supply-chain) | neo4j | supplychain123 |
| Grafana | admin | admin123 |

## Documentation

| Document | Topic |
|----------|-------|
| [01_business_requirements.md](docs/01_business_requirements.md) | Use cases, stakeholders, governance |
| [02_architecture.md](docs/02_architecture.md) | System architecture, design patterns |
| [03_platform_blueprint.md](docs/03_platform_blueprint.md) | Platform blueprint, target architecture, specs, and backlog |
| [04_data_platform.md](docs/04_data_platform.md) | Kafka schema, Neo4j graph model |
| [05_ai_agents.md](docs/05_ai_agents.md) | MCP, Skills, ReAct, LangGraph agents |
| [06_quality_assurance.md](docs/06_quality_assurance.md) | Testing strategy, contract tests |
| [07_cicd_automation.md](docs/07_cicd_automation.md) | CI/CD, Helm, Compose, minikube, tech matrix |
| [08_operation_runbook.md](docs/08_operation_runbook.md) | Operations, troubleshooting, Makefile |
| [09_supply_chain_domain.md](docs/09_supply_chain_domain.md) | Supply chain graph model, events |
| [10_healthcare_landscape.md](docs/10_healthcare_landscape.md) | Industry AI landscape analysis |
| [ADRs](docs/adrs/README.md) | Architecture Decision Records |

## Project Layout

```
container/            Docker Compose orchestration files
deploy/               Helm charts, Docker Compose, monitoring
docs/                 Full documentation suite
domains/              Domain agents, scripts, skills, webapps
monitoring/           Prometheus, Grafana, alerting configs
platform/             Streaming infrastructure (Flink, producers, ontology)
scripts/              Cross-domain validation, shared lib
```

## Safety Disclaimer

**Synthetic demo data only.** Not clinical software, not a medical device. All LLM answers are advisory-only and require independent clinical review before any action.
