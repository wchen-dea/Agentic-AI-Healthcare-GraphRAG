# Agentic AI Healthcare GraphRAG

A production-grade, multi-agent healthcare intelligence platform that combines streaming event processing, hybrid GraphRAG retrieval, and agentic AI orchestration to deliver real-time clinical decision support.

Built on Kafka, PyFlink, Qdrant, Neo4j, LangGraph, FastAPI, and Ollama — the system processes healthcare events in real time, builds a patient-centric knowledge graph with pharmacovigilance safety rules, and answers clinical questions using grounded evidence from both semantic search and graph traversal.

The first domain is **Healthcare Provider**; a parallel **Supply Chain Resilience** domain ships alongside it under `domains/supply-chain/`.

## Why This Platform

Healthcare AI systems fail when they rely solely on LLM prompting without deterministic clinical evidence. This platform solves that by combining three capabilities that most AI prototypes lack:

1. **Streaming-first evidence freshness** — events are queryable within seconds of arrival, not after overnight batch jobs.
2. **Hybrid retrieval with deterministic safety rules** — drug interactions, contraindications, and lab-to-condition signals are graph edges with mechanism annotations, not probabilistic guesses.
3. **Multi-agent specialist reasoning** — LangGraph routes medication safety, lab interpretation, and coding review queries to domain-specific agents that extract structured risk chains before LLM synthesis.

### Practical Value

| Stakeholder | What the platform delivers |
| --- | --- |
| Clinical teams | Real-time risk signals: drug interaction alerts with mechanism explanations, lab-confirmed contraindication chains, adverse event correlation across active medications |
| Pharmacists | Polypharmacy safety review: 41 seeded interaction rules, 23 contraindication rules, and 46 adverse reaction rules evaluated against the patient's current medication orders and lab results |
| Revenue cycle analysts | Coding gap detection: conditions present in the graph but missing ICD-10 mappings, flagged before claim submission |
| Population health teams | Cohort risk stratification from cross-patient graph traversal and vector similarity |
| Engineering teams | A reusable multi-domain blueprint: add a new domain by extending topic contracts, graph models, and enrichment rules without modifying the platform core |

### AI Trends Alignment

| Trend | How this platform implements it |
| --- | --- |
| Agentic AI | LangGraph StateGraph with 8 specialized agents, conditional routing, and confidence-gated re-retrieval loops — not a single-prompt wrapper |
| GraphRAG | Hybrid vector + graph retrieval with deterministic evidence ranking before LLM synthesis — grounding answers in both semantic similarity and explicit clinical relationships |
| Multi-modal retrieval | Qdrant semantic similarity + Neo4j relationship traversal combined in every query response — two complementary evidence channels, not one |
| Tool-use protocols (MCP) | 10 MCP tools embedded in the agents service with role-based authorization, SHA-256 audit hashing, and response budget enforcement |
| Evaluation-driven AI | MLflow tracing with 6 healthcare-specific scorers, cross-mode comparison, and evaluation harness ready for CI-gated release |
| Agent harness engineering | Retry with backoff, input/output guardrails, prompt injection detection, prompt versioning, tool wrappers, and context budget accounting |
| Local-first AI | Full stack runs on a laptop with zero API fees; Ollama provider abstraction ready for managed provider routing |
| Streaming AI pipelines | Kafka + PyFlink continuous enrichment with Avro schema governance — events queryable in seconds, not overnight batch |

## Summary

This project provides a domain-agnostic AI platform blueprint across three dimensions:

- **Technical depth**: streaming-first ingestion, dual evidence stores (vector + graph), multi-agent orchestration (LangGraph), and agent-ready APIs (REST + MCP) on shared domain modules.
- **Industry applicability**: one reusable architecture for clinical, operational, financial, and supply chain AI workflows with domain-specific specialist agents.
- **Implementation maturity**: complete local development stack with 133 automated tests, MLflow tracing, 48-medication pharmacovigilance knowledge graph, and production deployment configuration.

Repository intent:

- Root-level Docker Compose, default credentials, and local env examples are for development and synthetic-demo use only.
- Production readiness in this repository refers to the deployment configuration assets under `deploy/production/`, not to the root local stack defaults.

Production boundary in this repository:

- In scope: agents (embedded MCP), provider-web, separate monitoring config.
- Out of scope: source data systems, Confluent Kafka platform, and Apache Flink platform (independently managed).

## Tech Stack

- Streaming: Apache Kafka, Confluent Schema Registry, Apache Flink (PyFlink)
- Data Stores: Qdrant (vector), Neo4j (graph)
- API and AI: FastAPI + embedded FastMCP, Ollama (local-first)
- Frontend: Static provider web app (Nginx-served)
- Agent Orchestration: LangGraph multi-agent StateGraph, LangChain tools
- Observability: Prometheus, Grafana, Blackbox Exporter, MLflow Tracing, LangSmith
- Operations and Tooling: Docker Compose, Conduktor, NeoDash

## What This Repository Runs

A complete healthcare intelligence pipeline — from synthetic event generation to grounded AI answers — running entirely on a laptop:

```
Synthetic events → Kafka → PyFlink enrichment → Qdrant + Neo4j dual sinks
                                                        ↓
Clinical question → Multi-agent triage → Vector + Graph retrieval
                                                        ↓
                    Specialist agents → Evidence ranking → LLM synthesis → Answer
```

Concrete capabilities out of the box:

- Generates realistic clinical events (notes, labs, medications, claims, device telemetry) across 48 medications and 18 lab panels.
- Streams and enriches events in real time through a native PyFlink DataStream job.
- Builds a patient-centric knowledge graph with drug interactions, adverse reactions, contraindications, and lab-to-condition signals.
- Answers clinical questions using multi-agent reasoning with explainable evidence from both vector similarity and graph relationships.
- Provides a provider-facing web UI, MCP tool integration, and full observability stack.

## Healthcare Domain Readiness

The platform is reusable by design: core platform layers stay stable while domain behavior is added through topic contracts, enrichment rules, graph models, and prompt policy.

| Healthcare Section | Example Data Sources | Typical Outcomes |
| --- | --- | --- |
| Clinical Operations | EHR notes, labs, telemetry | Earlier risk detection, clinician-ready summaries |
| Revenue Cycle | Claims, coding events, prior-auth records | Denial reduction, coding consistency insights |
| Payer and Utilization | Claims timelines, authorization decisions | Utilization trend detection, anomaly triage |
| Population Health | Longitudinal encounters, chronic-condition signals | Cohort risk stratification, outreach prioritization |
| Medication Safety | Orders, interaction knowledge base, FAERS adverse event reporting | Real-time adverse event detection, contraindication alerts, drug-drug interaction mechanism tracing, pharmacovigilance signal ranking |
| Device and Remote Monitoring | Device telemetry, alerts, maintenance events | Faster anomaly response, operational efficiency |

## Supply Chain Domain

The supply-chain domain runs in parallel using its own Neo4j instance, Qdrant collection, and Kafka topics while sharing the existing Kafka cluster, Schema Registry, and monitoring stack.

| Supply Chain Section | Example Data Sources | Typical Outcomes |
| --- | --- | --- |
| Supplier Risk | Supplier profiles, geopolitical data, financial signals | Single-source detection, geopolitical exposure alerts |
| Procurement | Purchase orders, incoterms, lead time baselines | PO lifecycle tracking, cost variance analysis |
| Logistics | Shipment tracking, customs, transport mode | Delay detection, carrier performance, customs hold alerts |
| Quality | Inbound inspections, defect rates, CAPA records | Supplier quality scoring, rejection trend analysis |
| Disruption | Facility alerts, natural disaster, cyber incidents | Cascade impact assessment, mitigation status tracking |
| Inventory | Warehouse levels, reorder points, days-of-supply | Stockout risk detection, reorder optimization |

Launch supply-chain alongside healthcare:

```bash
docker compose -f container/docker-compose.infra.yml \
  -f container/docker-compose.healthcare.yml \
  -f container/docker-compose.supply-chain.yml \
  up -d
```

Supply-chain service endpoints:

| Service | URL |
| --- | --- |
| Neo4j Browser (SC) | http://localhost:7475 |
| Neo4j Bolt (SC) | bolt://localhost:7688 |
| Qdrant (SC) | http://localhost:6335 |

## Innovation Highlights

| Category | Capability |
| --- | --- |
| **Streaming intelligence** | Kafka + PyFlink continuous processing with Avro schema-governed contracts; events queryable in seconds |
| **Hybrid GraphRAG** | Qdrant vector evidence + Neo4j relationship context in every answer; deterministic evidence ranking before LLM synthesis |
| **Multi-agent orchestration** | LangGraph StateGraph with 8 nodes: triage → retrieval → specialist agents (medication safety, lab interpretation, coding review) → confidence evaluation → synthesis |
| **Pharmacovigilance knowledge graph** | 41 drug interaction edges with mechanism annotations, 46 adverse reaction edges with MedDRA terms, 23 contraindication edges — all deterministic, not probabilistic |
| **Explainability** | API returns `vector_context`, `graph_context`, `retrieval_plan`, `agent_trace`, and `confidence` alongside every answer |
| **Tool protocol** | 10 MCP tools with role-based authorization, SHA-256 audit hashing, and response budget enforcement |
| **Evaluation framework** | MLflow tracing with nested spans (CHAIN → AGENT → RETRIEVER → LLM) and 6 healthcare scorers for cross-mode comparison |
| **Domain scalability** | Add new domains (supply chain, insurance, cybersecurity) by extending topic contracts, graph models, and enrichment rules — platform core stays stable |
| **Local-first AI** | Full stack runs on a laptop with zero API fees; Ollama provider abstraction ready for managed providers |

## Runtime Summary

```text
Shared Infrastructure
  Kafka cluster (3 brokers) + Schema Registry
  Flink cluster (shared JobManager + TaskManager)
  Ollama LLM | Prometheus + Grafana | MLflow

Data Platform (per domain)
  Producer -> Kafka -> Flink job -> Qdrant + Neo4j

AI Agents (per domain)
  FastAPI agents service
    -> request classification + retrieval planning
    -> vector retrieval (Qdrant) + graph retrieval (Neo4j)
    -> evidence ranking + harness guards
    -> query mode: single-pass | ReAct | LangGraph multi-agent
    -> LLM synthesis (Ollama) + embedded MCP (/mcp)

Ops/UI
  Flink dashboard | Conduktor | Prometheus + Grafana
  MLflow Tracing UI | Neo4j Browser + NeoDash | Provider Web
```

## LLM Strategy

- Local default: Ollama using OLLAMA_URL and OLLAMA_MODEL.
- Production: OpenAI (primary) with Anthropic (fallback) via `LLM_PROVIDER` and `LLM_FALLBACK_PROVIDER`.
- LLM calls are routed through a provider abstraction in `domains/healthcare/agents/llm_provider.py` (`OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `FallbackProvider`).
- Prompt construction and synthesis logic are in `domains/healthcare/agents/domain/synthesis.py`.
- Active latency and output controls: LLM_TIMEOUT_SECONDS, LLM_MAX_TOKENS, LLM_TEMPERATURE.
- Production uses OpenAI (primary) with Anthropic (fallback); dev defaults to local Ollama.

### Ollama Cost Model (Local)

- Local Ollama inference has no per-token or per-request API fee.
- Local operating costs still exist (hardware, power, and maintenance time).
- If you move Ollama to cloud VMs, cloud compute/storage/network costs apply.
- If you switch to managed providers (Anthropic/OpenAI), provider token pricing applies.

## Key Capabilities

### Clinical Intelligence

- **Hybrid retrieval**: semantic nearest-neighbor evidence from Qdrant combined with patient-centric relationship context from Neo4j — every answer is grounded in both similarity and explicit clinical relationships.
- **14-rule lab signal engine**: each lab result is evaluated against clinical thresholds at ingest time (`MAY_INDICATE` edges written to Neo4j). Covers Hyperkalemia, AMI, CKD, Anemia, Hyperlipidemia, Hypothyroidism, and 8 more conditions.
- **FAERS-aligned pharmacovigilance**: adverse event detection fires after every clinical note by matching symptoms against `HAS_KNOWN_REACTION` graph edges for the patient's active medications.
- **Drug safety knowledge graph**: 41 `INTERACTS_WITH` edges with mechanism annotations, 46 `HAS_KNOWN_REACTION` edges with MedDRA terms, 23 `CONTRAINDICATED_FOR` edges — seeded at startup from `data-platform/healthcare/neo4j/generated_ontology_seeds.cypher`.

### Agentic AI

- **Three query orchestration modes**: single-pass (default), ReAct iterative loop, and LangGraph multi-agent — all coexisting behind feature flags.
- **Specialist agents**: medication safety, lab interpretation, and coding review agents extract structured risk data that single-pass pipelines cannot.
- **Confidence-gated retrieval**: low-confidence results trigger re-retrieval loops bounded by configurable iteration limits.
- **Skills layer**: business goals map to agent → skill → tool chains through a runtime planning API.

### Platform and Operations

- **48-medication catalog** with active ingredients, 18 lab-test panels with per-test abnormality thresholds, device alerts, CPT procedures, and claims financial fields.
- **10 MCP tools** with role-based authorization, evidence redaction, and response budget enforcement.
- **MLflow tracing** with nested spans across all query modes and 6 healthcare-specific evaluation scorers.
- **97 automated tests**: contract tests, planner evaluation, ReAct controller, LangGraph agent routing, MLflow integration, and polypharmacy scenario validation.
- **ICD-10 coding gap detection**: conditions present in the graph but missing coded diagnoses, surfaced before claim submission.
- **Full observability**: Prometheus metrics, Grafana dashboards, MLflow Tracing UI, Flink dashboard, Conduktor, and JSON audit logs.

## Query Orchestration Modes

The rag-api supports three query orchestration modes, selectable via environment variables:

| Mode | Env Variable | Response Metadata | Description |
| --- | --- | --- | --- |
| Single-pass (default) | (none) | `retrieval_plan` | Classify → plan → vector + graph → rank → synthesize |
| ReAct loop | `RAG_API_REACT_ENABLED=true` | `react` block | Iterative retrieval with confidence gating |
| LangGraph multi-agent | `RAG_API_LANGGRAPH_ENABLED=true` | `langgraph` block | Specialist agents with conditional routing |

LangGraph takes priority over ReAct when both are enabled. All three modes share the same retrieval (`domain/retrieval.py`), ranking (`domain/evidence.py`), synthesis (`domain/synthesis.py`), and response policy (`domain/response_policy.py`) modules.

## Multi-Agent Use Case: Polypharmacy Medication Safety

The primary multi-agent demonstration scenario is a polypharmacy medication safety review. This is where the LangGraph multi-agent mode delivers the most value over single-pass:

**Scenario:** A patient on Warfarin + Aspirin + Lisinopril + Spironolactone with Chronic Kidney Disease and elevated Potassium (6.1 mmol/L).

**Agent activation chain:**
1. `triage_agent` classifies as `medication_safety`
2. `vector_retrieval_agent` finds medication_order and lab_result events
3. `graph_retrieval_agent` returns interactions, contraindications, lab signals, adverse events
4. `medication_safety_agent` extracts the causal chain: Warfarin+Aspirin bleeding risk, dual potassium-sparing contraindication confirmed by lab
5. `confidence_evaluator` confirms dual-channel evidence (1.0)
6. `synthesis_agent` generates a grounded answer citing the mechanism chain

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Review medication safety: are there dangerous interactions or contraindications for this patient given their current labs and conditions?",
    "patient_id": "patient-0001"
  }' | jq '{request_type, answer, interactions: [.graph_context[0].interactions[]?], contraindications: [.graph_context[0].contraindications[]?], lab_signals: [.graph_context[0].lab_signals[]?]}'
```

Additional multi-agent query examples are in `domains/healthcare/scripts/query_examples.sh` under the `MultiAgent-*` and `DualPath-MultiAgent-*` sections.

## Skills Layer And Agent Skills Packages

This repository includes a runtime Skills layer plus generated Agent Skills packages.

- Runtime planner config: `domains/healthcare/agents/config/skills_layer.json`
- Runtime resolver: `domains/healthcare/agents/skills_layer.py`
- REST endpoint: `POST /skills/plan`
- MCP tool: `skills_plan_get`
- Generated Agent Skills packages: `domains/healthcare/skills/`, `domains/supply-chain/skills/`

Generate and validate skill packages:

```bash
python domains/healthcare/scripts/generate_agent_skills.py
python domains/healthcare/scripts/generate_agent_skills.py --check
python domains/healthcare/scripts/validate_agent_skills.py

python domains/supply-chain/scripts/generate_agent_skills.py
python domains/supply-chain/scripts/generate_agent_skills.py --check
python domains/supply-chain/scripts/validate_agent_skills.py
```

## MCP Quick Verify

```bash
curl -s http://localhost:8000/mcp/health | jq .
python3 ./domains/healthcare/scripts/mcp_smoke_test.py
```

## Quick Start

This quick start is for local development only. It is not a production deployment path.

Prerequisites:

- Docker Desktop or Docker Engine with Compose support
- [uv](https://docs.astral.sh/uv/) (Python project manager)
- jq (recommended for shell validations)
- make (for Makefile shortcuts)
- Enough disk for Ollama model download (roughly 5 GB+)

Start the full stack:

```bash
cd /path/to/Agentic-AI-Healthcare-GraphRAG
cp .env.example .env
make up          # or: make up-hc (healthcare only) / make up-sc (supply-chain only)
```

Or without the Makefile:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build
```

### Local Python Environment

The project uses [uv](https://docs.astral.sh/uv/) with Python 3.11 (same version as all Docker images).

```bash
uv sync              # Install all dependencies into .venv
uv run python ...    # Run scripts with the project Python
uv run pytest ...    # Run tests
```

### Makefile Shortcuts

```bash
make help        # Show all available targets
make up          # Start infra + healthcare + supply-chain
make up-hc       # Start infra + healthcare only
make up-sc       # Start infra + supply-chain only
make down-all    # Stop everything
make build       # Build healthcare images (default)
make build-all   # Build all images (healthcare + supply-chain)
make ps          # Show running containers
make neo4j-hc    # Open healthcare Neo4j shell
make neo4j-sc    # Open supply-chain Neo4j shell
make query-hc    # Run healthcare query examples
make query-sc    # Run supply-chain query examples
make test-hc     # Run healthcare validation tests
make test-sc     # Run supply-chain validation tests
make topics      # List all Kafka topics
make logs        # Tail healthcare logs
make pull-model  # Pull the Ollama LLM model
make fresh       # Full clean restart with both domains
```

The local stack follows the same externalized configuration pattern as the production bundle: copy `.env.example` to `.env` and keep local credentials and secret-like values in `.env`, not hardcoded in source-controlled Compose overrides.

Startup ordering in the local stack is intentionally gated:

- Schema Registry must report healthy before topic initialization runs.
- Topic initialization must complete before the producer starts.
- The producer also waits and retries until Schema Registry is reachable before schema registration.

### Local Secret Configuration

For local development, configure secret-like values in `.env` only.

1. Create a local env file:

```bash
cp .env.example .env
```

2. Edit `.env` and set the local values you want to use, especially:

- `NEO4J_PASSWORD`
- `CONDUKTOR_POSTGRES_PASSWORD`
- `CONDUKTOR_ADMIN_PASSWORD`
- `GRAFANA_ADMIN_PASSWORD`

3. Keep `.env` local only. It is ignored by git and should not be committed.

4. Recreate or restart affected services after changing secret-bearing values:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build
```

The values in `.env.example` are development placeholders. Replace them in `.env` if you want non-default local credentials.

Local Kafka topology after startup:

- broker 1: `localhost:9092`
- broker 2: `localhost:9093`
- broker 3: `localhost:9094`

If your local stack was created before the move to three brokers, existing Kafka topics may still have replication factor `1` because topic creation is idempotent. To fully reprovision the local Kafka cluster with replication factor `3`, recreate the local Kafka state when it is safe to do so:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml down -v
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --build
```

Pull the LLM model used by the API:

```bash
docker exec -it infra-ollama ollama pull llama3.1
```

Optional one-shot validation:

```bash
./scripts/validate_docs.sh
./scripts/validate_all_stacks.sh
./domains/healthcare/scripts/query_examples.sh
python3 ./domains/healthcare/scripts/mcp_smoke_test.py
```

CI-safe ReAct/planner validation (without full contract suite):

```bash
./domains/healthcare/scripts/test_react_planner.sh
```

### Optional: Enable ReAct Query Loop (Local)

The default query path is single-pass. To enable the iterative ReAct controller locally,
set these `.env` values and recreate `rag-api`:

```bash
RAG_API_REACT_ENABLED=true
RAG_API_REACT_MAX_ITERS=3
RAG_API_REACT_MIN_CONFIDENCE=0.75
RAG_API_REACT_MAX_NO_PROGRESS_STEPS=1
```

Then rebuild/recreate the API service:

```bash
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml build rag-api
docker compose -f container/docker-compose.infra.yml -f container/docker-compose.healthcare.yml up -d --force-recreate rag-api
```

When enabled, `/query` responses include an optional `react` block with loop metadata
(`iterations`, `final_reason`, `confidence`, and `actions`).

### Optional: Enable LangGraph Multi-Agent Mode (Local)

The LangGraph mode replaces the single-pass/ReAct pipeline with a multi-agent StateGraph that routes through specialized agents (triage, retrieval, medication safety, lab interpretation, coding review, confidence evaluation, synthesis).

```bash
RAG_API_LANGGRAPH_ENABLED=true
LANGGRAPH_MAX_ITERATIONS=3
```

When enabled, `/query` responses include a `langgraph` block with agent trace metadata.
LangGraph takes priority over ReAct when both are enabled.

See [docs/10_langgraph_comparison.md](docs/10_langgraph_comparison.md) for architecture details.

### Optional: Enable MLflow Tracing (Local)

MLflow traces all query modes (single-pass, ReAct, LangGraph) with nested span hierarchies.

```bash
MLFLOW_TRACKING_URI=http://localhost:5000
MLFLOW_EXPERIMENT_NAME=healthcare-graphrag
```

MLflow UI is available at http://localhost:5000 when the infra stack is running.
Tracing activates automatically and has zero overhead when `MLFLOW_TRACKING_URI` is unset.

## LocalStack

The local stack also includes `localstack` for development scenarios that need an AWS-compatible local endpoint surface.

LocalStack endpoint:

- Edge endpoint: `http://localhost:4566`

Basic health check:

```bash
curl -s http://localhost:4566/_localstack/health | jq .
```

Use this service for local-only integration and smoke testing. It is separate from the production deployment bundle and should not be interpreted as a production AWS configuration pattern.

## Service Endpoints

| Service | URL |
| --- | --- |
| RAG API docs | <http://localhost:8000/docs> |
| RAG API health | <http://localhost:8000/health> |
| RAG API metrics | <http://localhost:8000/metrics> |
| RAG API skills plan | <http://localhost:8000/skills/plan> |
| MCP server endpoint | <http://localhost:8000/mcp> |
| MCP diagnostic health | <http://localhost:8000/mcp/health> |
| Provider web app | <http://localhost:8088> |
| Flink UI | <http://localhost:8082> |
| Conduktor Console | <http://localhost:8085> |
| Schema Registry subjects | <http://localhost:8081/subjects> |
| Neo4j Browser | <http://localhost:7474> |
| NeoDash | <http://localhost:5005> |
| Qdrant dashboard | <http://localhost:6333/dashboard> |
| LocalStack edge endpoint | <http://localhost:4566> |
| Prometheus | <http://localhost:9090> |
| Grafana | <http://localhost:3000> |
| MLflow UI | <http://localhost:5000> |

## Default Credentials

These credentials are development-only defaults for the local stack. They must not be used as-is in any production or shared environment.

Neo4j:

```text
username: neo4j
password: healthcare123
bolt url: neo4j://localhost:7687
```

Conduktor:

```text
email: admin@healthcare.local
password: Admin@123!
```

Grafana:

```text
username: admin
password: admin123
```

## Verifying Flink Job Submission

The stack should submit exactly one application job by default:

- HealthcareGraphRagPyFlinkJob

Check with:

```bash
curl -s http://localhost:8082/jobs/overview | jq .
```

You should see HealthcareGraphRagPyFlinkJob in RUNNING state and no demo job auto-submission service.

## Conduktor Message View Setup

Because Kafka values are published using Confluent Avro wire format, configure Conduktor topic deserializers as:

- key: `String`
- value: `Avro (Schema Registry)`

If value deserializer is set to `Bytes`, message rendering and masking rules will fail.

## Query Examples

The script `domains/healthcare/scripts/query_examples.sh` runs representative GraphRAG queries including multi-agent polypharmacy safety scenarios:

```bash
make query-hc
# or directly:
./domains/healthcare/scripts/query_examples.sh
```

Direct API call example:

```bash
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why might this patient have hyperkalemia risk and what evidence exists?",
    "patient_id": "patient-0001"
  }' | jq .
```

## Project Layout

```text
pyproject.toml  Unified Python project config (uv, dependencies, ruff)
Makefile        Local development shortcuts (make up, make test-hc, etc.)
.python-version Python 3.11 pin (used by uv and Docker images)
data-platform/  Data platform: shared libraries and per-domain streaming infrastructure
  shared/       Shared modules (embedding, storage, runner, rules engine, ontology loader)
    webapp/     Shared webapp assets (styles, query-helpers.js, nginx config)
  healthcare/   Healthcare data sourcing
    config/     Ontology YAML, rules, vocabulary mappings
    flink-app/  PyFlink job, processor logic, graph writes
    neo4j/      Constraints and seed graph relationships
    producer/   Synthetic event producer
    schemas/    Avro envelope schema
  supply-chain/ Supply-chain data sourcing
    config/     Ontology YAML, risk signal rules
    flink-app/  Stream processor and graph writes
    neo4j/      Constraints and seed data
    producer/   Synthetic event producer
    schemas/    Avro envelope schema
domains/        Domain AI implementations
  healthcare/   Healthcare Provider AI domain
    agents/     Healthcare AI agents (FastAPI + MCP + LangGraph)
      domain/    Retrieval, synthesis, response policy, planner, harness
      langgraph_agents/  LangGraph multi-agent orchestration and MLflow tracing
    skills/     Generated Agent Skills packages
    scripts/    Domain-specific validation and query scripts
    webapp/     Provider-facing static UI
  supply-chain/ Supply Chain Resilience AI domain
    agents/     Supply-chain AI agents (FastAPI + skills layer)
    skills/     Agent Skills packages
    scripts/    Domain-specific validation and query scripts
    webapp/     Supply-chain query UI
container/docker-compose.infra.yml        Shared infrastructure (Kafka, ZK, monitoring, Ollama)
container/docker-compose.healthcare.yml   Healthcare domain services
container/docker-compose.supply-chain.yml Supply-chain domain services
docs/           Architecture, Kafka contract, graph model, and runbook
docs/adrs/      Architecture Decision Records (ADRs)
scripts/        Cross-domain validation scripts
monitoring/     Prometheus, Grafana, alerting, and blackbox config
deploy/         Deployment bundles (production AI runtime and monitoring)
```

## Implementation Notes

- `app.py` is the composition root: settings, client initialization, HTTP routes, and MCP tools. Business logic is extracted into `domain/` modules.
- `domain/retrieval.py` contains embedding, vector search (Qdrant), and graph search (Neo4j Cypher).
- `domain/synthesis.py` handles prompt construction and LLM synthesis via the provider abstraction.
- `domain/response_policy.py` contains response sanitization, truncation, budget enforcement, and confidence estimation.
- `domain/planner.py` and `domain/evidence.py` handle request classification and deterministic evidence ranking.
- `langgraph_agents/` provides multi-agent orchestration (LangGraph StateGraph), MLflow tracing, and evaluation.
- `llm_provider.py` provides the provider abstraction with `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, and `FallbackProvider`.
- flink-app submits a native PyFlink DataStream job (healthcare_graph_rag_pyflink_job.py) to Flink JobManager.
- healthcare_graph_rag_job.py is retained as a fallback processing implementation and provides reusable sink/enrichment logic consumed by the PyFlink job.
- Schema Registry stores MedicalEvent Avro schemas and Kafka payloads are published with Confluent Avro serialization (schema ID on wire).
- healthcare.dlq.events is created but not actively written by the processor yet.
- API model resolution falls back to available Ollama tags (for example llama3.1:latest) when needed.
- Docker Compose files live under `container/`; build contexts and volume mounts use `../` to resolve paths relative to the repository root.

## Documentation

| Document | Purpose |
|----------|---------|
| [docs/02_architecture.md](docs/02_architecture.md) | System architecture, design patterns, component diagrams |
| [docs/adrs/README.md](docs/adrs/README.md) | Architecture Decision Records index |
| [docs/06_technical_specs.md](docs/06_technical_specs.md) | Container inventory, library versions, API specification |
| [docs/01_business_specs.md](docs/01_business_specs.md) | Use cases, business rules, stakeholders, AI governance |
| [docs/04_kafka_schema.md](docs/04_kafka_schema.md) | Kafka topic topology, Avro schema, payload examples |
| [docs/05_neo4j_model.md](docs/05_neo4j_model.md) | Graph model, node labels, relationships, pharmacovigilance |
| [docs/07_mcp_layer_design.md](docs/07_mcp_layer_design.md) | MCP tool contracts, schemas, rollout phases |
| [docs/08_skills_layer.md](docs/08_skills_layer.md) | Skills layer flow, generated packages, and validation |
| [docs/10_langgraph_comparison.md](docs/10_langgraph_comparison.md) | Multi-agent architecture comparison (single-pass vs ReAct vs LangGraph) |
| [docs/11_healthcare_ai_agent_landscape.md](docs/11_healthcare_ai_agent_landscape.md) | Industry AI agent landscape analysis and platform alignment |
| [docs/13_runbook.md](docs/13_runbook.md) | Operations runbook, health checks, failure modes |
| [docs/12_ai_qa.md](docs/12_ai_qa.md) | QA strategy, contract tests, graph validation, accuracy |
| [deploy/README.md](deploy/README.md) | Deployment: dev (minikube), production (k8s + compose) |
| [domains/supply-chain/README.md](domains/supply-chain/README.md) | Supply Chain domain: graph model, events, quick start |
| [Makefile](Makefile) | Local development shortcuts (make up, make test-hc, etc.) |
| [pyproject.toml](pyproject.toml) | Unified Python project config (uv, dependencies, ruff) |

## Safety Disclaimer

**This project uses synthetic demo data only.** It is not clinical software, not a medical device, and not intended for diagnosis, treatment, or patient care. All LLM-generated answers carry an advisory-only safety caveat and must not be acted upon as clinical directives without independent clinical review.
