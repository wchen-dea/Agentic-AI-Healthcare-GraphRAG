# ADR-0004: Embed FastMCP in rag-api

- Status: accepted
- Date: 2026-06-26

## Context

The project exposes two API surfaces:

- RAG REST API for application clients.
- FastMCP API for agent/tool clients.

Running a separate MCP service adds deployment complexity and duplicate runtime concerns for local development.

## Decision

Embed FastMCP in the same rag-api process and expose MCP at `/mcp`.

- RAG REST remains at `/query`.
- Human diagnostic endpoint remains at `/mcp/health`.
- `mcp-server/` remains as a standalone reference scaffold, not default runtime.

## Consequences

Positive:

- Single API container for local stack.
- Shared retrieval/generation logic between REST and MCP surfaces.
- Simpler compose topology.

Trade-offs:

- Shared process resources across REST and MCP traffic.
- Requires careful route and lifecycle handling for MCP streamable HTTP.

## Related

- [Architecture](../architecture.md)
- [MCP Layer Design](../mcp_layer_design.md)
- [Runbook](../runbook.md)
