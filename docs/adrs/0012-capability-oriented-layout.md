# ADR-0012: Capability-Oriented Layout and Shared Agent Core

- Status: accepted (Phase 1 implemented; Phases 2–4 planned)
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
   | 2 | `git mv` `rag-api` → `agent-service` and `healthcare_rag_api` → `healthcare_agent`; split `app.py`, `domain/`, and `langgraph_agents/` into the capability folders; adopt `AgentServiceSettings`; remove the legacy non-LangGraph query path |
   | 3 | Move `platform/shared` → `packages/knowledge-core` and switch Flink images to the wheel; move ontology/skills under `knowledge/`; merge infra folders under `infra/` |
   | 4 | Split tests into `unit`/`integration`/`evals`; make ruff blocking in CI; remove shims; apply the same layout to supply-chain |

   Old import paths remain as thin re-export modules until Phase 4. New code must import from the target location.

## Consequences

- Positive: governance primitives (authorization, audit, injection defence, stream contract) have one tested implementation that every domain reuses.
- Positive: lost audit events are now visible through `rag_api_audit_write_failures_total{tool}` and an error log that includes the trace id. Requests still succeed when the audit sink fails.
- Positive: folder names map onto ADR-0010 layers, so ownership and review scope are clear.
- Negative: renames in Phase 2 touch imports, Dockerfiles, Helm values, CI paths, and docs in one change. Do it in one commit with `git mv` to keep history.
- Negative: shims add temporary indirection until Phase 4.
- Neutral: the audit JSON key set is unchanged. Key order differs (`timestamp` is now last), which JSON consumers must not rely on.

## Phase 1 Changes

- New workspace member `packages/agent-core`, registered in the root `pyproject.toml` and required by `healthcare-rag-api`, with unit tests (`make test-core`).
- `healthcare_rag_api.langgraph_agents.runtime` re-exports the runtime contract from `agent_core.runtime` and keeps the process-wide binding.
- `healthcare_rag_api.domain.guardrails` uses core injection and length checks and keeps the healthcare topic and output rules.
- `healthcare_rag_api.app` uses `ToolPolicy`, `JsonlAuditSink`, `hash_payload`, `format_sse`, and `SSE_HEADERS` from core.
- Both rag-api Dockerfiles mount the agent-core `pyproject.toml` for workspace discovery. The healthcare image builds and installs the `agent-core` wheel.
- CI (`rag-api-contracts.yml`) runs agent-core tests and triggers on `packages/**`. `deploy-ai-prd.yml` also triggers on `packages/**`.

## Follow-ups

- Replace the dev-only role header with verified caller identity (OIDC/JWT claims mapped to roles) behind `ToolPolicy`.
- Adapt `mlflow_tracing` to the `Tracer` port and Qdrant/Neo4j clients to `VectorStore`/`GraphStore` (Phase 2).
- Unify the duplicate injection rules in `domain/harness.py` with `agent_core.guardrails` (Phase 2).
