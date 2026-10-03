# Agentic AI Healthcare + Supply Chain GraphRAG

This repository implements a local-first, multi-domain GraphRAG platform for healthcare and supply-chain workloads. The code is organized as a uv workspace with shared runtime packages, domain-specific agent services, streaming pipelines, knowledge assets, and web apps.

The platform is intentionally provider-neutral and modular: it can run locally with Ollama and MiniLM in development and switch to Databricks-hosted embeddings and LLMs in production without changing the app contract.

## Architecture

```mermaid
flowchart LR
    UI[Healthcare / supply-chain web apps] --> API[FastAPI agent service]
    API --> ORCH[LangGraph orchestration]
    ORCH --> RETR[Vector + graph retrieval]
    RETR --> NEO4J[(Neo4j)]
    RETR --> QDRANT[(Qdrant)]
    ORCH --> MCP[MCP tools + skills]
    ORCH --> GEN[LLM provider router]
    KAFKA[Kafka topics] --> FLINK[Flink enrichment]
    FLINK --> QDRANT
    FLINK --> NEO4J
    MON[MLflow / Grafana / Prometheus] --> API
    MON --> ORCH
```

## Quickstart

Use the Makefile for the default local workflow.

```bash
make up
make api-hc
make query-hc
make validate-docs
```

Common targets:

- `make up` starts the shared infra plus both domains.
- `make up-hc` starts the healthcare domain.
- `make up-sc` starts the supply-chain domain.
- `make validate` runs stack validation.
- `make validate-docs` runs markdownlint.
- `make test-unit` runs unit tests across the workspace.
- `make lint` runs Ruff checks.

## Domains

| Domain | Core focus | Key runtime |
| --- | --- | --- |
| Healthcare | drug safety, lab interpretation, coding review, patient summaries | `domains/healthcare/agent-service`, Flink jobs, Neo4j, Qdrant |
| Supply chain | logistics, inventory and disruption analysis | `domains/supply-chain/agent-service`, Flink jobs, Neo4j, Qdrant |

## Repository layout

```text
.
├── Makefile
├── pyproject.toml
├── uv.lock
├── docs/
├── domains/
│   ├── healthcare/
│   └── supply-chain/
├── packages/
│   ├── agent-core/
│   └── knowledge-core/
├── infra/
│   ├── compose/
│   ├── helm/
│   └── observability/
├── scripts/
├── README.md
└── docs/adrs/
```

## Documentation index

| Document | Purpose |
| --- | --- |
| [docs/01_business_requirements.md](docs/01_business_requirements.md) | Business scope, personas and requirements |
| [docs/02_architecture.md](docs/02_architecture.md) | System architecture and runtime model |
| [docs/03_platform_blueprint.md](docs/03_platform_blueprint.md) | Target platform blueprint and backlog |
| [docs/04_data_platform.md](docs/04_data_platform.md) | Kafka, Flink, Neo4j, Qdrant and embeddings |
| [docs/05_ai_agents.md](docs/05_ai_agents.md) | Agent orchestration, request types, memory, MCP and guardrails |
| [docs/06_quality_assurance.md](docs/06_quality_assurance.md) | QA strategy, evaluations and MLflow gates |
| [docs/07_cicd_automation.md](docs/07_cicd_automation.md) | CI/CD and release flow |
| [docs/08_operation_runbook.md](docs/08_operation_runbook.md) | Operations, troubleshooting and re-indexing |
| [docs/09_supply_chain_domain.md](docs/09_supply_chain_domain.md) | Supply-chain domain architecture |
| [docs/10_healthcare_landscape.md](docs/10_healthcare_landscape.md) | Healthcare reference patterns and gaps |
| [docs/adrs/README.md](docs/adrs/README.md) | Architecture decision index |

## ADRs

The ADRs describe the major architectural decisions behind the platform:

- [ADR-0001](docs/adrs/0001-dual-persistence-qdrant-neo4j.md) — dual persistence with Qdrant and Neo4j
- [ADR-0002](docs/adrs/0002-qdrant-streaming-vector-store.md) — streaming vector store choice
- [ADR-0003](docs/adrs/0003-ontology-governance-and-seed-generation.md) — ontology governance and seed generation
- [ADR-0004](docs/adrs/0004-local-first-llm-provider-routing.md) — local-first routing with provider fallback
- [ADR-0005](docs/adrs/0005-embed-fastmcp-in-rag-api.md) — embedded MCP server in the API
- [ADR-0006](docs/adrs/0006-skills-layer-standardization-and-validation.md) — skills-layer standardization
- [ADR-0007](docs/adrs/0007-langgraph-multi-agent-orchestration.md) — multi-agent orchestration with LangGraph
- [ADR-0008](docs/adrs/0008-mlflow-tracing-and-evaluation.md) — observability and MLflow evaluation
- [ADR-0009](docs/adrs/0009-domain-module-extraction.md) — extraction of domain-specific modules
- [ADR-0010](docs/adrs/0010-layered-agentic-architecture.md) — layered runtime architecture
- [ADR-0011](docs/adrs/0011-uv-workspace-packaging.md) — uv workspace packaging
- [ADR-0012](docs/adrs/0012-capability-oriented-layout.md) — capability-oriented repository layout

## Related

- [docs/05_ai_agents.md](docs/05_ai_agents.md) for the runtime behavior of the agents
- [docs/04_data_platform.md](docs/04_data_platform.md) for the ingestion and persistence model
- [docs/08_operation_runbook.md](docs/08_operation_runbook.md) for deployment and operations
- [docs/06_quality_assurance.md](docs/06_quality_assurance.md) for evaluation gates and validation
