# ADR-0008: MLflow Tracing and Evaluation for Agent Pipelines

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The healthcare rag-api supports three query orchestration modes (single-pass, ReAct, LangGraph multi-agent). Each mode has different agent topologies, latency profiles, and evidence assembly patterns. Comparing their effectiveness requires:

- per-query pipeline tracing with nested spans (agent, retriever, LLM),
- healthcare-specific evaluation scorers,
- cross-mode comparison in a single experiment tracker,
- zero overhead when tracing is disabled.

Prometheus metrics capture aggregate latency and throughput. JSON audit logs capture per-request authorization and outcome. Neither provides the span-level detail needed to debug agent routing decisions, measure per-retriever latency, or score answer quality across a dataset.

LangSmith was already integrated for LangGraph-specific tracing, but it requires a SaaS API key and does not trace single-pass or ReAct modes.

## Decision

Integrate MLflow as the tracing and evaluation backend for all three query modes. Activation is controlled by `MLFLOW_TRACKING_URI`; when unset, all tracing wrappers pass through with zero overhead.

Tracing architecture:

- `trace_query()` wraps any query function in a root `CHAIN` span with mode, patient, and request-type attributes.
- `trace_agent_node()` wraps LangGraph agent nodes in `AGENT` spans.
- `trace_llm_call()` wraps LLM synthesis in an `LLM` span.
- `trace_retriever()` wraps vector and graph retrieval in `RETRIEVER` spans.
- `@mlflow_trace` is a general-purpose decorator for any function.

Evaluation harness (`mlflow_eval.py`):

- Six healthcare-specific scorers: routing accuracy, agent coverage, evidence completeness, answer quality, safety caveat, latency.
- Scoring primitives are shared with `evaluation.py` to avoid duplication; `mlflow_eval.py` wraps them as float-returning functions and adds safety-caveat and latency scorers.
- `run_mlflow_evaluation()` logs per-case and aggregate metrics to an MLflow experiment.
- `compare_modes()` runs multiple query functions and logs a comparison artifact.

Infrastructure:

- MLflow server deployed as `infra-mlflow` in `docker-compose.infra.yml` (port 5000, SQLite backend, local artifact storage).
- `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT_NAME` are configured on the rag-api service in `docker-compose.healthcare.yml`.

## Consequences

Positive:

- Every query mode is traceable with the same span schema.
- Evaluation scorers can be run offline (without MLflow) or logged to MLflow experiments.
- MLflow UI provides visual trace inspection, experiment comparison, and metric trending.
- LangSmith and MLflow can run concurrently for LangGraph queries.

Trade-offs:

- Adds `mlflow>=2.21.0` dependency (~50 MB installed).
- SQLite backend in the local stack is not suitable for production; PostgreSQL is recommended.
- Tracing adds per-request overhead when enabled (typically < 5 ms per span).
- LangSmith and MLflow serve overlapping purposes for LangGraph; teams should choose one for production.

## Alternatives Considered

- LangSmith only: rejected because it does not trace single-pass or ReAct modes and requires a SaaS API key.
- OpenTelemetry: rejected because the project already uses Prometheus for metrics; adding OTel tracing would require a separate collector and backend without the built-in evaluation and experiment-comparison features of MLflow.
- Custom trace logging: rejected to avoid maintaining a bespoke tracing format when MLflow provides a standard span model and UI.

## Rollout and Verification

- Set `MLFLOW_TRACKING_URI=http://mlflow:5000` in `.env` and rebuild `rag-api`.
- Verify MLflow is reachable: `curl -s http://localhost:5000/health`
- Run a query and check the MLflow Tracing UI at `http://localhost:5000` for new spans.
- Run evaluation: `python -c "from langgraph_agents.mlflow_eval import compare_modes; print('ok')"`
- Run tests: `python -m pytest domains/healthcare/rag-api/tests/test_mlflow_integration.py`

## Related

- [ADR-0007: LangGraph multi-agent query orchestration](./0007-langgraph-multi-agent-orchestration.md)
- [domains/healthcare/rag-api/langgraph_agents/mlflow_tracing.py](../../domains/healthcare/rag-api/langgraph_agents/mlflow_tracing.py)
- [domains/healthcare/rag-api/langgraph_agents/mlflow_eval.py](../../domains/healthcare/rag-api/langgraph_agents/mlflow_eval.py)
- [container/docker-compose.infra.yml](../../container/docker-compose.infra.yml) (MLflow service)
