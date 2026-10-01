# ADR-0012: Capability-Oriented Layout and Shared Agent Core

- Status: accepted (Phases 1–4 implemented)
- Date: 2026-10-01
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

ADR-0010 set the runtime layers (React UI → BFF → LangGraph orchestration → agents → MCP tools). ADR-0011 packaged the APIs as a uv workspace. The folder structure and module names did not follow either decision:

- `domains/healthcare/rag-api` is named after one retrieval technique. It actually hosts the BFF, orchestration, agents, MCP tools, guardrails, evaluation, and audit.
- `healthcare_rag_api/domain/` holds 20+ unrelated modules: guardrails, retrieval, routing, evaluation, memory, budgets, harness, and LLM providers. `app.py` is about 1,400 lines and is the settings loader, policy engine, audit writer, SSE encoder, and every route at once.
- Domain-neutral concerns are reimplemented per domain: tool policy, audit events, prompt-injection rules, the SSE contract, and runtime ports. Supply-chain would have to copy them again.
- Infrastructure is spread across `container/`, `deploy/`, and `monitoring/`. Shared streaming code sits in `platform/shared`, which is a generic name.
- Audit write failures were swallowed without a log or a metric, which hides gaps in a regulated audit trail.

## Decision

1. **Use the capability-oriented target layout below.** Each folder name says what the code does, not which library it uses.

   ```text
   packages/
     agent-core/            # agent_core: provider-neutral contracts and governance primitives
     knowledge-core/        # (was platform/shared) streaming, embedding, ontology, storage
   domains/healthcare/
     agent-service/         # (was rag-api) distribution healthcare-agent-service
       src/healthcare_agent/
         api/               # FastAPI BFF routes, request/response schemas, SSE endpoint
         orchestration/     # LangGraph graph, state, planner, routing
         agents/            # specialist agent nodes
         tools/             # MCP tool definitions and the tool gateway
         retrieval/         # vector and graph retrieval adapters (VectorStore/GraphStore)
         generation/        # LLM providers, prompts, model routing, synthesis
         safety/            # guardrails, PHI handling, grounding checks
         evaluation/        # quality gates and online evaluation
         config/            # Settings composition (agent_core.settings + domain fields)
       tests/{unit,integration,evals}/
     web/                   # (was webapp)
     data-pipelines/        # producers and Flink jobs
     knowledge/             # ontology, skills, seed data
     evals/datasets/
     scripts/
   infra/{compose,helm,observability}/   # merges container/, deploy/, monitoring/
   ```

2. **Introduce `packages/agent-core` (`agent_core`).** This is a workspace member that depends only on pydantic and pydantic-settings, with no FastAPI, LangGraph, or cloud SDK imports. It owns:

   | Module | Contract |
   | --- | --- |
   | `runtime` | `AgentRuntime` and the vector/graph/synthesis call protocols used by orchestration nodes |
   | `ports` | `VectorStore`, `GraphStore`, `LLMProvider`, `SessionStore`, `Tracer` protocols and `NoopTracer` |
   | `policy` | `ToolPolicy` (role → tool allow-list, deny-all when the file is missing) and `AuthorizationError` |
   | `audit` | `AuditEvent`, `AuditSink`, `JsonlAuditSink` (hash-only inputs, failure callback), `hash_payload` |
   | `guardrails` | `GuardrailResult`, prompt-injection detection, input length check |
   | `streaming` | SSE event types, frame encoder, response headers (ADR-0010 stream contract) |
   | `settings` | `AgentServiceSettings` (typed env configuration shared by agent services) |

   Domain services keep domain rules (topic scope, clinical output safety, grounding) and compose the core primitives.

3. **Naming rules.**
   - Distributions use kebab case and import packages use snake case: `healthcare-agent-service` / `healthcare_agent`.
   - Folders are named after capabilities (`retrieval`, `safety`), not techniques or vendors (`rag`, `langgraph_agents`).
   - Vendor adapters live under the capability they implement, for example `retrieval/qdrant.py` and `generation/bedrock.py`.
   - No `utils`, `common`, or `domain` catch-all modules.

4. **Migrate in phases with compatibility shims.** Each phase keeps all tests green and is independently deployable.

   | Phase | Scope |
   | --- | --- |
   | 1 (done) | Add `agent-core`; healthcare delegates policy, audit, guardrail base, SSE, and runtime contracts to it; audit failures are logged and counted |
   | 2 (done) | `git mv` `rag-api` → `agent-service` and `healthcare_rag_api` → `healthcare_agent`; split `app.py`, `domain/`, and `langgraph_agents/` into the capability folders; adopt `AgentServiceSettings`; remove the legacy non-LangGraph query path |
   | 3 (done) | Move `platform/shared` → `packages/knowledge-core` and switch Flink images to the wheel; move ontology/skills under `knowledge/`; merge infra folders under `infra/` |
   | 3b (done) | Rename ops identifiers (`RAG_API_*` env prefix, `rag_api_*` metrics, Helm chart/k8s service `rag-api`, compose container, `rag-api-contracts.yml`, `rag-api.env`) with a deprecation window that accepts the old env names |
   | 4 (done) | Split tests into `unit`/`integration`/`evals`; make ruff blocking in CI; remove shims; apply the same layout to supply-chain |

   Phase 2 moved modules without re-export shims: the service is deployed only as a wheel, and no external code imports the old paths. New code must import from the target location.

## Consequences

- Positive: governance primitives (authorization, audit, injection defence, stream contract) have one tested implementation that every domain reuses.
- Positive: lost audit events are now visible through `agent_service_audit_write_failures_total{tool}` (named `rag_api_audit_write_failures_total` before Phase 3b) and an error log that includes the trace id. Requests still succeed when the audit sink fails.
- Positive: folder names map onto ADR-0010 layers, so ownership and review scope are clear.
- Negative: renames in Phase 2 touch imports, Dockerfiles, Helm values, CI paths, and docs in one change. Do it in one commit with `git mv` to keep history.
- Negative: Phase 2 has no import shims, so out-of-tree scripts that imported `healthcare_rag_api.*` must be updated.
- Neutral: the audit JSON key set is unchanged. Key order differs (`timestamp` is now last), which JSON consumers must not rely on.

## Phase 1 Changes

- New workspace member `packages/agent-core`, registered in the root `pyproject.toml` and required by the healthcare service, with unit tests (`make test-core`).
- `healthcare_rag_api.langgraph_agents.runtime` (now `healthcare_agent.orchestration.runtime`) re-exports the runtime contract from `agent_core.runtime` and keeps the process-wide binding.
- `healthcare_rag_api.domain.guardrails` (now `healthcare_agent.safety.guardrails`) uses core injection and length checks and keeps the healthcare topic and output rules.
- `healthcare_rag_api.app` uses `ToolPolicy`, `JsonlAuditSink`, `hash_payload`, `format_sse`, and `SSE_HEADERS` from core.
- Both rag-api Dockerfiles mount the agent-core `pyproject.toml` for workspace discovery. The healthcare image builds and installs the `agent-core` wheel.
- CI (`rag-api-contracts.yml`) runs agent-core tests and triggers on `packages/**`. `deploy-ai-prd.yml` also triggers on `packages/**`.

## Phase 2 Changes

- `domains/healthcare/rag-api` → `domains/healthcare/agent-service` and `healthcare_rag_api` → `healthcare_agent`, with `git mv` so history is kept. The distribution is `healthcare-agent-service`, with `[tool.uv.build-backend] module-name = "healthcare_agent"` because the names differ. The ASGI entry is `healthcare_agent.main:app`.
- Module moves:

  | New location | Old location |
  | --- | --- |
  | `main.py` (composition root only) | `app.py` |
  | `config/settings.py` (`HealthcareAgentSettings`) | `Settings` in `app.py` |
  | `api/schemas.py`, `api/routes.py`, `api/governance.py`, `api/responses.py` | request models, routes, policy/audit, and response shaping in `app.py` |
  | `tools/mcp_server.py` (`HealthcareMcpTools`) | `@mcp.tool()` functions in `app.py` |
  | `orchestration/query_service.py` (`QueryService`) | `run_query` in `app.py` |
  | `observability/metrics.py`, `observability/tracing.py` | Prometheus collectors in `app.py`, `langgraph_agents/mlflow_tracing.py` |
  | `generation/factory.py` | provider and router construction in `app.py` |
  | `orchestration/{graph,state,runtime}.py`, `agents/nodes.py`, `agents/registry.py`, `tools/langchain_tools.py` | `langgraph_agents/` |
  | `orchestration/{planner,memory,plan_types}.py`, `retrieval/{search,ranking}.py`, `generation/{model_router,synthesis,structured_output}.py`, `safety/{guardrails,harness,response_policy}.py`, `evaluation/{gates,grounding_scorecard,retrieval_benchmark}.py` | `domain/` |
  | `generation/providers.py`, `tools/skills.py`, `evaluation/{langsmith,mlflow_eval}.py` | `llm_provider.py`, `skills_layer.py`, `langgraph_agents/{evaluation,mlflow_eval}.py` |

- `HealthcareAgentSettings` extends `agent_core.settings.AgentServiceSettings` with store, model-gateway, MCP, skills, and MLflow fields. `neo4j_password` is a `SecretStr`. `tool_policy_path` and `skills_layer_path` default to the files packaged in `healthcare_agent/config/`, and relative paths resolve against the package. Environment variable names are unchanged.
- Request-size limits that depend on settings (`max_question_chars`, `max_context_items`) are checked by field validators against `RequestLimits`, which the composition root sets. This keeps the schemas importable without settings. As a result, OpenAPI no longer shows `maxLength` for `question` or the maximum for `top_k`.
- HTTP and MCP share one path. `QueryService.run_query` / `stream` always run the LangGraph graph. `/query` passes `RAG_API_MAX_CONTEXT_ITEMS` to the triage agent as `context_limit` instead of a hard-coded 5. The default is still 5.
- Removed: the legacy single-pass query path, the ReAct controller, `RAG_API_LANGGRAPH_ENABLED`, and `RAG_API_REACT_*`. The flags are also removed from the deploy env files and Helm values. There is no rollback flag; roll back by redeploying the previous image.
- `domains/healthcare/scripts/test_react_planner.sh` → `test_planner.sh`.
- Ops names were kept until Phase 3b (see below): the `RAG_API_*` env prefix, the `rag_api_*` metrics, the Helm chart and k8s service `rag-api`, the compose container `healthcare-rag-api`, and the CI workflow `rag-api-contracts.yml`.

## Phase 3 Changes

- Path moves (all with `git mv`):

  | New location | Old location |
  | --- | --- |
  | `packages/knowledge-core` (import `knowledge_core`) | `platform/shared` (`shared_lib`) |
  | `domains/<d>/knowledge/{ontology,graph-seeds,skills}` | `domains/<d>/{ontology,graph-seeds,skills}` |
  | `domains/<d>/data-pipelines/{flink-job,producer}` | `domains/<d>/{flink-job,producer}` |
  | `infra/compose/docker-compose.*.yml` | `container/docker-compose.*.yml` |
  | `infra/helm` | `deploy/helm` |
  | `infra/environments/{dev,production}` | `deploy/{dev,production}` |
  | `infra/observability` | `monitoring` |

- `knowledge-core` is a uv workspace member with `requires-python >=3.10`, because the `flink:1.20` image ships Python 3.10. The wheel is pure Python (`py3-none-any`).
- The Flink job and Flink cluster Dockerfiles build the `knowledge-core` wheel in a `uv` builder stage and `pip install` it. They no longer copy shared source into `/app/shared`.
- Domain scripts and tests resolve paths from their own location (`Path(__file__).parents[n]`) instead of the repo root. The Flink `ontology_loader.ontology_dir()` checks `config/ontology`, `knowledge/ontology`, and `ontology` while walking up parents. `ONTOLOGY_CONFIG_DIR` still overrides it.
- The healthcare webapp image builds in a mirrored repo path (`/src/domains/healthcare/webapp`) and copies the agent-service `skills_layer.json`, so the vitest contract-drift test runs inside the image.
- Compose files, `setup-minikube.sh`, the Makefile, CI workflows, `scripts/validate_docs.sh`, the README, and docs 01–09 use the new paths. Historical ADRs (0004–0011) are not edited.
- Local data in `container/volume/` is untracked and unchanged.

## Phase 3b Changes

Healthcare ops identifiers now match the `agent-service` name. Supply-chain names are unchanged until Phase 4.

| Area | Before | After |
|---|---|---|
| Env prefix | `RAG_API_*` | `AGENT_*` (old names still read, see below) |
| Prometheus metrics | `rag_api_*` | `agent_service_*` (hard rename; Grafana dashboard updated) |
| Default audit log | `logs/rag_api_audit.log`, `/var/log/rag-api/audit.log` | `logs/agent_audit.log`, `/var/log/agent-service/audit.log` |
| Helm subchart / k8s Deployment and Service | `rag-api` | `agent-service` (values key `agent-service:`, `--set agent-service.secrets.*`) |
| Image repository | `...-graphrag-rag-api` | `...-graphrag-agent-service` |
| Compose service / containers | `rag-api`, `healthcare-rag-api`, `dev-rag-api` | `agent-service`, `healthcare-agent-service`, `dev-agent-service` |
| Env files | `infra/environments/*/rag-api.env*` | `infra/environments/*/agent-service.env*` |
| Prometheus jobs | `rag_api`, `blackbox_rag_api_health` | `agent_service`, `blackbox_agent_service_health` |
| CI workflow | `rag-api-contracts.yml` | `agent-service-contracts.yml` |
| Script base URL | `RAG_API_URL` | `AGENT_SERVICE_URL` (falls back to `RAG_API_URL`) |

- Deprecation window: `agent_core.settings.env_alias()` maps each field to `AliasChoices("AGENT_<x>", "RAG_API_<x>")`. The new name wins when both are set. A single warning per process lists every legacy name in use. The aliases are removed in Phase 4.
- Not renamed: the `runtime_tools` value `"rag_api"` in `skills_layer.json` and generated skills. It is part of the skills contract.
- Risks at cutover:
  - The metric rename breaks continuity of dashboards and alerts that query `rag_api_*` history.
  - Renaming the k8s Deployment and Service creates new objects and deletes the old ones, so there is a short gap. Revert with `helm rollback`.
  - A branch-protection rule that requires the old `rag-api-contracts` check name must be updated.
  - Old local logs stay in `rag-api/logs/`.

## Phase 4 Changes

Supply-chain now has the same layout and governance as healthcare, the deprecation shims are gone, and CI enforces test tiers and lint.

| Area | Before | After |
|---|---|---|
| Supply-chain service | `domains/supply-chain/rag-api`, `supply_chain_rag_api` (`app.py`, `domain/`, `langgraph_agents/`, `react_controller.py`) | `domains/supply-chain/agent-service`, distribution `supply-chain-agent-service`, package `supply_chain_agent` with `api/`, `orchestration/`, `agents/`, `retrieval/`, `generation/`, `safety/`, `tools/`, `evaluation/`, `observability/`, `config/` and a `main.py` composition root |
| Supply-chain query path | single-pass / ReAct / LangGraph modes | LangGraph only, through `QueryService`, with role-based `ToolPolicy`, guardrails and JSONL audit |
| Shared governance | per-domain policy, audit and metrics wiring | `agent_core.governance.ToolGovernance` and `agent_core.metrics.ServiceMetrics` (`agent-core[metrics]`) |
| Env names | `AGENT_*` with `RAG_API_*` aliases; `RAG_API_URL`, `SC_RAG_API_URL`, `SC_SKILLS_LAYER_PATH` | `AGENT_*` only; scripts use `AGENT_SERVICE_URL` / `SC_AGENT_SERVICE_URL` |
| Supply-chain compose / CI | `sc-rag-api`, `supplychain-rag-api` | `sc-agent-service`, `supplychain-agent-service`; image `sc-agent-service-contracts:ci` |
| Skills `runtime_tools` | `"rag_api"` | `"agent_service"` (skills regenerated for both domains) |
| Tests | flat `tests/` | `tests/unit`, `tests/integration`, `tests/evals`; `make test-unit`, `test-integration`, `test-evals`; separate CI steps |
| Lint | advisory | blocking `ruff-lint` CI job and `make lint` (E, F, I; E501 left to formatting) |

- The supply-chain image now builds the `agent-core` wheel alongside the service wheel.
- The supply-chain skills layer referenced three MCP tools that did not exist (`disruption_impact_analyze`, `quality_trend_summarize`, `inventory_status_get`). They now point at implemented tools, and `tests/unit/test_tool_catalog.py` in each domain fails on future drift between skills, tool policy and MCP tools.
- Breaking changes:
  - `RAG_API_*`, `SC_RAG_API_URL` and `SC_SKILLS_LAYER_PATH` are ignored. Rename them in env files and secrets before deploying.
  - Supply-chain `/query` returns 401 for roles without the `query` grant, 422 for unknown request fields, and new LangGraph output keys (`retrieval_plan`, `guardrails`, `langgraph`, `trace_id`).
  - CI step and job names changed; update branch-protection rules that require them.
- Not renamed: the supply-chain webapp `localStorage` keys `rag_api_base` / `rag_api_mode`, to keep users' saved settings.

## Follow-ups

- Replace the dev-only role header with verified caller identity (OIDC/JWT claims mapped to roles) behind `ToolPolicy`.
- Adapt `observability/tracing.py` to the `Tracer` port and the Qdrant/Neo4j clients to `VectorStore`/`GraphStore` (`retrieval/qdrant.py`, `retrieval/neo4j.py`).
- Unify the duplicate injection rules in `safety/harness.py` with `agent_core.guardrails`.
- Move the remaining library-level `os.getenv` reads into `HealthcareAgentSettings`. They are in `retrieval/search.py` (`EMBEDDING_MODEL`), `orchestration/memory.py`, `orchestration/graph.py` (`LANGGRAPH_MAX_ITERATIONS`, LangSmith), `generation/model_router.py` (`ModelTierConfig.from_env`), `generation/providers.py`, and `observability/tracing.py`.
- Remove the drifted copies of `ontology_loader`, `rules_engine`, `runner`, and `storage` in the healthcare Flink app in favour of `knowledge_core`.
- Remove the try/except import fallback in the supply-chain Flink job now that `knowledge_core` is always installed.
