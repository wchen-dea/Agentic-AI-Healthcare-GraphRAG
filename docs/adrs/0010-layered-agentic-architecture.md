# ADR-0010: Use a layered agentic architecture

- Status: accepted
- Date: 2026-09-30
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The runtime stack spans UI, API orchestration, graph execution, provider integration, governance and tools. The project needed a single layered model that captured the actual runtime without coupling low-level concerns to the UI or API shell.

## Decision

Adopt a layered runtime model: UI → BFF/API → orchestration → domain agents → tools and providers. Guardrails, audit, stream encoding and runtime contracts are handled as shared primitives, while domain-specific behavior stays in the service layer.

## Consequences

Positive:

- Boundaries are clear and reviewable.
- The same runtime model can scale across domains.
- Governance and shared contracts are reused rather than re-implemented.

Trade-offs:

- More explicit interfaces mean more code to maintain.
- A layered model requires careful contract discipline.
- Refactors can take multiple phases to land cleanly.

## Alternatives Considered

- Single app module: simple but impossible to govern at scale.
- Vendor-bound architecture: couples runtime behavior to one stack.

## Rollout and Verification

- Define the runtime contracts first.
- Move the domain and governance boundary code into the shared service layer.
- Validate the API contract with end-to-end tests and docs.

## Related

- [02_architecture.md](../02_architecture.md)
- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0012](0012-capability-oriented-layout.md)
