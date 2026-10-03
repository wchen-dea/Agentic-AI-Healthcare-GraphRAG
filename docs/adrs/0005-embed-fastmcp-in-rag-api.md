# ADR-0005: Embed FastMCP in rag-api

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

> **Current locations (post-ADR 0012):** `rag-api` / `healthcare_rag_api` is now `domains/healthcare/agent-service` (package `healthcare_agent`); shared governance, metrics, and settings live in `packages/agent-core/src/agent_core/`. The FastMCP server is `healthcare_agent/tools/mcp_server.py`.

## Context

The project exposes two API surfaces:

- RAG REST API for application clients.
- FastMCP API for agent/tool clients.

Running a separate MCP service adds deployment complexity and duplicate runtime concerns for local development.

## Decision

Embed FastMCP in the same rag-api process and expose MCP at `/mcp`.

- RAG REST remains at `/query`.
- Human diagnostic endpoint remains at `/mcp/health`.
- The standalone mcp-server scaffold has been removed; embedded MCP is the only runtime.

Implementation:

- Embedded MCP tools run in the same process as REST query orchestration.
- Ten MCP tools are exposed: `patient_context_get`, `vector_evidence_search`, `graphrag_answer_generate`, `risk_summary_generate`, `evidence_bundle_export`, `timeline_explain`, `medication_risk_assess`, `coding_gap_detect`, `cohort_risk_summary`, `skills_plan_get`.
- Skills planning is available through both REST (`POST /skills/plan`) and MCP (`skills_plan_get`).
- Tool policy gating is centralized in `domains/healthcare/agent-service/src/healthcare_agent/config/tool_policies.json`.

## Shared MCP Server Framework

Both domains (healthcare and supply-chain) build their embedded server through `packages/agent-core/src/agent_core/mcp_server.py` (install `agent-core[mcp]`):

- `build_mcp_server(settings, name=..., instructions=...)` creates `FastMCP` from `AgentServiceSettings`. Transport security is always passed explicitly so the localhost DNS-rebinding default never rejects Docker `Host` headers.
- Each domain declares a `TOOL_SPECS` tuple of `ToolSpec(name, title, description, annotations)` in `tools/mcp_server.py`. `register_tools` registers them with MCP tool annotations: `read_only` (read-only, idempotent, closed-world), `generation` (read-only, non-idempotent, open-world LLM call), and `export` (read-only, non-idempotent, closed-world).
- Tool methods stay synchronous and keep `governance.execute`. `register_tools` offloads each call to a worker thread with `anyio.to_thread`, so blocking Qdrant, Neo4j, and LLM calls do not stall the event loop that serves REST and SSE.
- `register_skills_surface` publishes the skills layer as MCP resources and a prompt:
  - `skills://catalog` lists business goals, default agents, and skills.
  - `skills://{skill_id}` returns one skill definition.
  - The prompt (`clinical_review` for healthcare, `supply_risk_review` for supply-chain) renders a grounded review plan for a business goal and an optional subject ID.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MCP_INSTRUCTIONS` | domain default | Overrides the server instructions sent at initialize |
| `MCP_STATELESS_HTTP` | `false` | Runs streamable HTTP without server-side sessions (for horizontal scaling) |
| `MCP_JSON_RESPONSE` | `false` | Returns JSON responses instead of SSE streams |
| `MCP_DNS_REBINDING_PROTECTION` | `false` | Validates `Host` and `Origin` headers |
| `MCP_ALLOWED_HOSTS` | empty | Comma-separated hosts allowed when protection is on |
| `MCP_ALLOWED_ORIGINS` | empty | Comma-separated origins allowed when protection is on |

Enable `MCP_DNS_REBINDING_PROTECTION` with explicit hosts and origins for any deployment reachable from a browser.

## Consequences

Positive:

- Single API container for local stack.
- Shared retrieval/generation logic between REST and MCP surfaces.
- Simpler compose topology.

Trade-offs:

- Shared process resources across REST and MCP traffic.
- Requires careful route and lifecycle handling for MCP streamable HTTP.

## Alternatives Considered

- Separate MCP service process: rejected because it duplicates retrieval and authorization logic and doubles the container count for local development.
- gRPC protocol instead of MCP: rejected because MCP provides a standard tool protocol with ecosystem compatibility for agent frameworks.

## Rollout and Verification

- Verify MCP health: `curl -s http://localhost:8000/mcp/health | jq .`
- Run MCP handshake smoke test: `python3 ./domains/healthcare/scripts/mcp_smoke_test.py`
- Contract tests in `domains/<domain>/agent-service/tests/integration/test_contracts.py` validate MCP tool shapes, annotations, skills resources, and prompts.
- Factory unit tests live in `packages/agent-core/tests/unit/test_mcp_server.py`.

## Related

- [ADR-0004: Local-first LLM with provider routing](./0004-local-first-llm-provider-routing.md)
- [Architecture](../02_architecture.md)
- [MCP Layer Design](../05_ai_agents.md)
- [Skills Layer](../05_ai_agents.md)
- [Runbook](../08_operation_runbook.md)
