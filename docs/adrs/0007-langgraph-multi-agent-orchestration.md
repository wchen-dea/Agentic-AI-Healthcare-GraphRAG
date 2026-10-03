# ADR-0007: Use LangGraph for multi-agent orchestration

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

A single-pass pipeline cannot handle varying clinical tasks such as medication safety, lab interpretation and coding review. The system needed a structured way to route requests to specialists, re-enter retrieval on low confidence and preserve state across turns.

## Decision

Adopt LangGraph as the shared orchestration engine. The graph keeps request state in typed structures, routes to specialist agents using conditional edges, and supports iterative retrieval and evaluation loops with bounded confidence checks.

## Consequences

Positive:

- Routing logic is explicit and testable.
- Specialist agents can be added or phased in with low risk.
- The same graph structure can support both healthcare and supply-chain use cases.

Trade-offs:

- The orchestration layer introduces more moving parts than a single pipeline.
- Graph configuration and state evolution must be carefully designed.
- A runtime loop can still mis-route or under-score confidence if the evaluator is weak.

## Alternatives Considered

- LangChain AgentExecutor or custom orchestration: more latency, more magic and weaker control.

## Rollout and Verification

- Enable the graph in default mode with edge-based routing.
- Validate the routing and confidence loops in unit and integration tests.
- Keep the single-pass path as a fallback while the graph matures.

## Related

- [05_ai_agents.md](../05_ai_agents.md)
- [06_quality_assurance.md](../06_quality_assurance.md)
- [ADR-0010](0010-layered-agentic-architecture.md)
