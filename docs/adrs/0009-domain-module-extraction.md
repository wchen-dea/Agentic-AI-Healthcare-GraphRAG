# ADR-0009: Extract domain modules from the API service

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The service originally mixed API routes, orchestration, retrieval, evaluation and governance in a single code path. This made the code harder to reason about, harder to test and harder to reuse across domains.

## Decision

Split the original service into domain-specific modules for API, retrieval, generation, safety, orchestration and evaluation. The extracted modules remain under the domain structure and expose a clean contract to the application entry point.

## Consequences

Positive:

- The codebase is easier to navigate.
- Teams can change a domain capability without touching unrelated runtime concerns.
- Testing and ownership are clearer.

Trade-offs:

- A large refactor requires careful import updates and migration planning.
- Cross-module contracts must remain stable.
- The initial churn may temporarily increase confusion.

## Alternatives Considered

- Keep everything in one service: simpler initially but growing technical debt.
- Create only a few giant utility files: still hard to maintain.

## Rollout and Verification

- Move modules in digestible staged pull requests.
- Update imports and config keys without adding shims unless required.
- Keep the API behavior stable while reorganizing the internal layout.

## Related

- [ADR-0010](0010-layered-agentic-architecture.md)
- [ADR-0012](0012-capability-oriented-layout.md)
- [03_platform_blueprint.md](../03_platform_blueprint.md)
