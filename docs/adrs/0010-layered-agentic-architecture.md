# ADR-0010: Layered Agentic Architecture

- Status: accepted
- Date: 2026-09-30
- Deciders: platform team
- Supersedes: none (amends [ADR-0007](0007-langgraph-multi-agent-orchestration.md))
- Superseded by: none

> **Current locations (post-ADR 0012):** `rag-api` / `healthcare_rag_api` is now `domains/healthcare/agent-service` (package `healthcare_agent`); shared governance, metrics, and settings live in `packages/agent-core/src/agent_core/`.

## Context

The healthcare rag-api grew three ways to answer the same question: single-pass, ReAct, and the LangGraph graph from ADR-0007. Each one handled guardrails, structured output, and session memory slightly differently. The LangGraph agents imported `app` directly to reach retrieval and synthesis, so the orchestrator was coupled to the HTTP process. The provider web UI (`domains/healthcare/webapp`) could only show a skeleton until a full synchronous `/query` finished.

We need an explicit target layering that:

- gives clinicians live, evidence-free progress while multi-agent work runs,
- enforces authorization and deterministic guardrails at one place, before any tool runs,
- lets specialist agents reach data only through a narrow, swappable tool-gateway port,
- leaves room for durable state, human approval, real identity, and per-domain MCP servers without a rewrite.

## Decision

Adopt the following layered architecture. Each layer talks only to the layer directly below it.

```text
┌───────────────────────────────────────────────────────────────┐
│ 1. React UI (Vite + TypeScript)  domains/healthcare/webapp    │
│    SSE client, runtime type guards, cancel, fallback to /query│
└──────────────────────────┬────────────────────────────────────┘
                           │ POST /query/stream (SSE) · POST /query
┌──────────────────────────▼────────────────────────────────────┐
│ 2. API / BFF (FastAPI)  agents/app.py                         │
│    authN/authZ, rate limits, audit, metrics, session memory,  │
│    SSE framing; composition root that binds the runtime port  │
└──────────────────────────┬────────────────────────────────────┘
                           │ run_langgraph_query / stream_langgraph_query
┌──────────────────────────▼────────────────────────────────────┐
│ 3. Orchestrator (LangGraph StateGraph)  langgraph_agents/     │
│    input_guardrail → triage → retrieval → specialists →       │
│    confidence loop → synthesis → output_guardrail             │
└──────────────────────────┬────────────────────────────────────┘
                           │ specialist nodes (subgraphs later)
┌──────────────────────────▼────────────────────────────────────┐
│ 4. Specialist agents  medication safety · labs · coding review│
└──────────────────────────┬────────────────────────────────────┘
                           │ AgentRuntime port (runtime.py)
┌──────────────────────────▼────────────────────────────────────┐
│ 5. Tool gateway → MCP servers (embedded today, per domain     │
│    and trust boundary later)                                  │
└──────────────────────────┬────────────────────────────────────┘
┌──────────────────────────▼────────────────────────────────────┐
│ 6. Data and models  Qdrant · Neo4j · LLM provider routing     │
└───────────────────────────────────────────────────────────────┘
```

Layer rules:

- **The UI holds no clinical logic.** It renders server responses after runtime narrowing (`src/api/guards.ts`) and persists only non-sensitive preferences.
- **The BFF owns policy.** It authorizes before streaming or tool execution, writes one audit entry per request (outcomes: success, denied, error, or cancelled), and never forwards exception text to clients.
- **The orchestrator owns control flow and guardrails.** The input guardrail short-circuits to `END` before any tool runs. The output guardrail withholds unsafe answers. Streamed `step` events carry only allowlisted scalar fields (`public_step`), never evidence or answer text.
- **Agents reach data only through `AgentRuntime`.** It exposes `vector_search`, `graph_search`, `synthesize`, and `synthesize_structured`, and the composition root binds it with `configure_runtime`. Tests bind a fake runtime, so the graph runs without live infrastructure.

The architecture is delivered in phases:

| Phase | Scope | Status |
| --- | --- | --- |
| P1 | `AgentRuntime` port; graph-level input/output guardrails, structured output, and session context; `POST /query/stream` SSE (`meta` → `step`* → `result` or `error`); webapp live agent steps with automatic `/query` fallback | Implemented |
| P2 | Durable Postgres checkpointer keyed by session, with a per-turn state reset (the `operator.add` reducers would otherwise accumulate evidence across turns); `interrupt()` for clinician approval of high-risk answers; a resume endpoint | Planned |
| P3 | BFF identity: OIDC sign-in, server-side session, and identity propagation to tools, replacing the trusted `X-Caller-Role` header | Planned |
| P4 | Split MCP servers by domain and trust boundary (for example clinical read, coding, admin) and add an MCP-client `AgentRuntime` adapter; promote specialists to subgraphs | Planned |
| P1 | LangGraph is the default orchestrator for `POST /query` and MCP tools (`RAG_API_LANGGRAPH_ENABLED` defaults to `true`; `false` is a rollback switch to single-pass/ReAct) | Implemented |
| Cleanup | Retire ReAct and single-pass once the MLflow evaluation set (ADR-0008) shows no regressions on the LangGraph path | Planned |

`POST /query` and `POST /query/stream` both use the LangGraph orchestrator by default, so streamed and synchronous answers come from the same graph. `/query/stream` always uses LangGraph. The UI's "Stream agent steps" setting only chooses between live progress and a single response.

## Consequences

Positive:

- One guardrail and policy path for orchestrated queries; blocked input never reaches retrieval.
- Clinicians see live progress (triage, retrieval, specialists, confidence) without exposing PHI-bearing evidence in progress events.
- Orchestration is testable in isolation through the runtime port (`tests/test_layered_runtime.py`).
- Later phases (checkpointer, identity, MCP split) plug in at defined seams instead of requiring a rewrite.

Trade-offs:

- The legacy single-pass and ReAct paths stay in the code as a rollback switch until cleanup, so there are still three code paths to maintain.
- LangGraph responses carry an `agent_trace`; the response budget sheds trace entries (then the trace summary) before shortening the answer.
- SSE needs proxies that do not buffer (the endpoint sends `X-Accel-Buffering: no`). Ingress timeouts must cover the longest graph run.
- A module-level runtime binding is a process-wide singleton. P4 should move to per-request injection if multiple runtimes per process are needed.
- FastMCP host validation stays a deployment risk until P4 separates MCP servers from the API host.

## Alternatives Considered

- **Durable workflow engine (Temporal) as the orchestrator:** strong durability, but heavy for sub-minute interactive queries. LangGraph checkpointing (P2) covers the approval and resume needs.
- **Independent agent microservices (A2A):** better isolation, but adds network hops, distributed tracing, and auth between agents before there is a scaling need. Per-domain MCP servers (P4) give the trust-boundary split at lower cost.
- **Managed agent hosting (Databricks Agent Framework, Amazon Bedrock Agents):** good for platform alignment. The provider-neutral runtime port keeps this open as an adapter rather than a rewrite.
- **WebSockets instead of SSE:** bidirectional, but the flow is request then server push. SSE works with standard HTTP auth, proxies, and `fetch` streaming.

## Rollout and Verification

- Backend: `cd domains/healthcare/rag-api && uv run --no-project --python 3.11 --with-requirements requirements.txt --with pytest --with httpx python -m pytest tests -q -p no:warnings` (contract tests cover stream success with audit, a denied caller returning 401, and an error event that does not leak details).
- Webapp: `npm run typecheck && npm test && npm run build` in `domains/healthcare/webapp` (covers stream parsing, deduplication, error events, and `/query` fallback on 404/405).
- Docs: `./scripts/validate_docs.sh`.
- Operations: monitor `outcome=cancelled` audit entries and stream latency, and set ingress read timeouts above `LANGGRAPH_MAX_ITERATIONS` × the worst-case node latency.

## Related

- [ADR-0005: Embed FastMCP in rag-api](0005-embed-fastmcp-in-rag-api.md)
- [ADR-0007: LangGraph multi-agent query orchestration](0007-langgraph-multi-agent-orchestration.md) (amended by this ADR)
- [ADR-0008: MLflow tracing and evaluation](0008-mlflow-tracing-and-evaluation.md)
- [02_architecture.md](../02_architecture.md), [05_ai_agents.md](../05_ai_agents.md)
- Code: `domains/healthcare/rag-api/langgraph_agents/runtime.py`, `langgraph_agents/graph.py`, `app.py` (`/query/stream`), `domains/healthcare/webapp/src/api/client.ts`
