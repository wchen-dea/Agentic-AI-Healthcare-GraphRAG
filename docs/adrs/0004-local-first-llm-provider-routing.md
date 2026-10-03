# ADR-0004: Use local-first LLM routing with provider fallback

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The platform must stay usable in local and cloud environments. It should default to a local model for development and allow production to switch to Databricks or cloud-hosted providers when scale and quality require it.

## Decision

Use provider-neutral config and a router that chooses the active LLM provider based on latency target, budget constraint and model tier. The default dev configuration uses local Ollama or a local embedding runtime, while production can route to Databricks or cloud endpoints as configured.

## Consequences

Positive:

- Local-first development keeps the environment flexible and low-cost.
- Fallback logic protects availability when one provider is degraded.
- Model routing separates business rules from provider SDK details.

Trade-offs:

- Provider behavior is not fully identical across vendors.
- Operational tuning is needed for latency and cost budgets.
- Fallbacks increase complexity when troubleshooting requests.

## Alternatives Considered

- Single provider only: simpler but poor resilience and poor local development ergonomics.
- Hard-coded provider selection in each service: brittle and duplicative.

## Rollout and Verification

- Configure latency and cost budgets in settings.
- Exercise fallback behavior in smoke tests and evals.
- Keep provider-specific logic isolated behind a router interface.

## Related

- [05_ai_agents.md](../05_ai_agents.md)
- [06_quality_assurance.md](../06_quality_assurance.md)
- [ADR-0008](0008-mlflow-tracing-and-evaluation.md)
