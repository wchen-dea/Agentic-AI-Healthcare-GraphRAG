# ADR-0008: Use MLflow for tracing and evaluation

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The platform needs observability for routing quality, evidence completeness, answer quality and latency without introducing a second tracing system. LangSmith was not required because MLflow already provides logging and evaluation hooks.

## Decision

Use MLflow as the single observability and evaluation backend for agent traces, offline evaluation and threshold-based quality gates. The evaluation harness scores request routing and answer quality so the team can compare modes and detect regressions.

## Consequences

Positive:

- Observability stays aligned with the project stack.
- The same metrics support both local runs and deployment checks.
- The gate checks are deterministic and reproducible.

Trade-offs:

- MLflow adds one more service to the stack.
- Evaluation quality depends on well-crafted scoring logic and datasets.
- A noisy score can create false confidence if not reviewed with business context.

## Alternatives Considered

- LangSmith only: not needed for the current workflow and adds another integration.
- Manual logs only: not reproducible and difficult to compare across versions.

## Rollout and Verification

- Log traces for routing and answer generation.
- Run evaluation gates before promotion and keep threshold rules in version control.
- Track latency and safety caveats in the same dashboard views.

## Related

- [06_quality_assurance.md](../06_quality_assurance.md)
- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0004](0004-local-first-llm-provider-routing.md)
