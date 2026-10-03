# ADR-0006: Standardize and validate the skills layer

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The project needed a common way to map business goals to tool chains and agent behavior. Without a formal skills layer, each domain would drift toward ad hoc prompts, tool selection and validation rules.

## Decision

Model the business logic in a skills layer that maps request types to agent actions, tool calls and validation constraints. The same layer is used by both healthcare and supply-chain services and is checked in CI for drift.

## Consequences

Positive:

- Shared agent behavior is easier to reason about.
- Skills make tool selection explicit and testable.
- The same interface can evolve without breaking each domain separately.

Trade-offs:

- Skills require maintenance when new workflows are introduced.
- A strong schema may slow exploratory changes.
- Validation logic must stay aligned with the runtime.

## Alternatives Considered

- Free-form prompt orchestration only: easier to start, harder to govern and review.
- Per-domain custom logic: duplicates effort and increases regressions.

## Rollout and Verification

- Generate and validate skill manifests for both domains.
- Run CI checks against the generated packages and tool maps.
- Review skill changes with any change to domain behavior.

## Related

- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0005](0005-embed-fastmcp-in-rag-api.md)
- [ADR-0012](0012-capability-oriented-layout.md)
