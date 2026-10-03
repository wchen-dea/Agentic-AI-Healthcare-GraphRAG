# ADR-0005: Embed FastMCP in the API layer

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The system needed governed tool access for retrieval, graph navigation and causal checks without creating a separate service for each tool. The API already owned request routing and policy enforcement, so a shared embedded MCP server was the natural seam.

## Decision

Integrate a FastMCP server into the agent service and expose a governed tool layer to the graph nodes. Tool access is filtered by policy and explicit tool metadata, which keeps the runtime auditable and reviewable.

## Consequences

Positive:

- The tool surface is governed in one place.
- Agent services can re-use the same MCP pattern across domains.
- Tool invocation remains close to the orchestration logic.

Trade-offs:

- The API must own more governance logic.
- Failure modes include tool-policy drift and broken tool registration.
- The framework requires clear versioning as tools evolve.

## Alternatives Considered

- Separate tool microservice: more operational overhead and latency.
- No MCP layer: harder to govern and test tools.

## Rollout and Verification

- Register tool policies and validate them in CI.
- Check role-based access at runtime before calling any tool.
- Exercise the end-to-end tool call path in integration tests.

## Related

- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0006](0006-skills-layer-standardization-and-validation.md)
- [ADR-0007](0007-langgraph-multi-agent-orchestration.md)
