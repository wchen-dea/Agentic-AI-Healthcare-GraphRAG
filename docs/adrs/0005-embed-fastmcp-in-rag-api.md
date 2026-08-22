# ADR-0005: Embed FastMCP in rag-api

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

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
- Tool policy gating is centralized in `domains/healthcare/agents/config/tool_policies.json`.

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
- Contract tests in `domains/healthcare/agents/tests/test_contracts.py` validate MCP tool shapes.

## Related

- [ADR-0004: Local-first LLM with provider routing](./0004-local-first-llm-provider-routing.md)
- [Architecture](../02_architecture.md)
- [MCP Layer Design](../05_ai_agents.md)
- [Skills Layer](../05_ai_agents.md)
- [Runbook](../09_runbook.md)
