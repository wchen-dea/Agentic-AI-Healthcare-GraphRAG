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

### Tracing contract

Tracing is enabled only when `MLFLOW_TRACKING_URI` is non-empty. `MLFLOW_EXPERIMENT_NAME` selects the experiment and defaults to `healthcare-graphrag`. When disabled, tracing wrappers are transparent pass-throughs and do not contact MLflow.

The healthcare agent emits:

- a parent `CHAIN` span for each query;
- `AGENT` spans for LangGraph nodes;
- `RETRIEVER` spans for vector and graph retrieval;
- an `LLM` span for answer generation; and
- configurable spans from `@mlflow_trace`.

Each span records bounded inputs/outputs where needed, operation-specific counts, latency, and an explicit success or error outcome. Exceptions are re-raised after bounded error metadata is recorded.

### Privacy contract

MLflow is treated as an operational data store. Span data must not contain unrestricted patient records, credentials, access tokens, or raw clinical payloads. `_safe_repr` limits size and nesting breadth but does not anonymize data. Implementations should use counts, approved identifiers, classifications, or hashes for correlation. Response guardrails and the audit log remain separate controls; MLflow does not replace either one.

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

- Start MLflow with the infrastructure stack and verify `make mlflow` returns `OK`.
- Set `MLFLOW_TRACKING_URI` and, optionally, `MLFLOW_EXPERIMENT_NAME` before starting the agent service.
- Execute a healthcare query and confirm the experiment contains the parent query span and its child agent, retriever, and LLM spans.
- Use the response `trace_id` to correlate the request with service logs and audit records; do not assume it is the MLflow UI's internal trace ID.
- Run evaluation gates before promotion and keep threshold rules in version control.
- Track latency and safety caveats in the same dashboard views.

## Related

- [06_quality_assurance.md](../06_quality_assurance.md)
- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0004](0004-local-first-llm-provider-routing.md)
