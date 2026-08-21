# ADR-0007: LangGraph Multi-Agent Query Orchestration

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The healthcare rag-api originally used a single-pass pipeline: classify request, retrieve from vector and graph stores, rank evidence, synthesize answer. ADR-0005 embedded MCP tools in rag-api. A feature-flagged ReAct controller added iterative retrieval but repeated the same fixed action each iteration without specialist reasoning.

Clinical queries vary significantly in what matters: medication safety questions need interaction and contraindication chain analysis, lab interpretation questions need abnormal-value extraction, and coding review questions need ICD-10 gap detection. A single pipeline treats all request types identically, leaving specialist reasoning to the LLM prompt alone.

The project needed a multi-agent architecture that:

- routes to domain-specialist agents based on request type,
- shares state across agents without circular imports,
- coexists with the single-pass and ReAct modes behind feature flags,
- supports observability through MLflow and LangSmith without coupling,
- reuses existing retrieval, ranking, and synthesis logic.

## Decision

Adopt LangGraph `StateGraph` as the multi-agent orchestration framework for the healthcare rag-api. The graph contains eight nodes connected by conditional edges:

- `triage_agent` — classifies request type and selects retrieval plan
- `vector_retrieval_agent` — Qdrant similarity search with evidence ranking
- `graph_retrieval_agent` — Neo4j patient graph traversal with evidence ranking
- `medication_safety_agent` — interaction, contraindication, and adverse event extraction
- `lab_interpretation_agent` — lab signal and abnormal observation extraction
- `coding_review_agent` — claims gap detection and ICD-10 mapping analysis
- `confidence_evaluator` — evidence completeness scoring and loop control
- `synthesis_agent` — grounded answer generation via the LLM provider

After graph retrieval, conditional routing dispatches to the appropriate specialist based on `request_type`. Patient summary and cohort queries skip specialist agents and proceed to confidence evaluation. Low-confidence results loop back to vector retrieval (bounded by `LANGGRAPH_MAX_ITERATIONS`, default 3).

Three query modes coexist:

| Mode | Activation | Priority |
| --- | --- | --- |
| Single-pass | Default (no env vars) | Lowest |
| ReAct | `RAG_API_REACT_ENABLED=true` | Medium |
| LangGraph | `RAG_API_LANGGRAPH_ENABLED=true` | Highest |

All modes share the same domain modules: `domain/retrieval.py`, `domain/synthesis.py`, `domain/evidence.py`, `domain/planner.py`, `domain/response_policy.py`.

Shared state is managed through `HealthcareAgentState`, a TypedDict with `Annotated` reducer fields using `operator.add` for append-only list merging across agent nodes.

## Consequences

Positive:

- Specialist agents extract structured risk data (interaction chains, contraindication-to-lab confirmation) that single-pass cannot.
- Each agent is independently testable without live infrastructure.
- Conditional routing avoids unnecessary specialist execution for simple queries.
- Feature flag allows gradual rollout without disrupting existing single-pass users.
- State reducers prevent data loss across retrieval iterations.

Trade-offs:

- Adds `langgraph`, `langchain-core`, and `langsmith` dependencies.
- Agent nodes use deferred imports from `app.py` for retrieval clients, creating a runtime dependency (not circular at import time).
- Confidence estimation remains simple (binary: both channels = 1.0); richer confidence models are future work.
- Specialist agents extract but do not independently reason — the LLM synthesis still produces the final answer.

## Alternatives Considered

- Extend the ReAct controller with action selection: rejected because the current ReAct implementation repeats the same action every iteration and the spec doc's richer behavior was never implemented.
- Use LangChain AgentExecutor: rejected because it requires LLM-based tool selection, adding latency and non-determinism to the routing decision.
- Custom agent framework: rejected to avoid maintaining a bespoke orchestration layer when LangGraph provides typed state, conditional edges, and ecosystem compatibility.

## Rollout and Verification

- Set `RAG_API_LANGGRAPH_ENABLED=true` in `.env` and rebuild `rag-api`.
- Verify with: `curl -s -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"Review medication safety for this patient","patient_id":"patient-0001"}' | jq '.langgraph'`
- Expected: non-null `langgraph` block with `agent_trace`, `iterations`, `confidence`.
- Run tests: `python -m pytest domains/healthcare/agents/tests/test_langgraph_agents.py`
- Polypharmacy scenario tests validate specialist agent activation and interaction chain extraction.

## Related

- [ADR-0005: Embed FastMCP in rag-api](./0005-embed-fastmcp-in-rag-api.md)
- [ADR-0004: Local-first LLM with provider routing](./0004-local-first-llm-provider-routing.md)
- [docs/langgraph_comparison.md](../langgraph_comparison.md)
- [domains/healthcare/agents/langgraph_agents/](../../domains/healthcare/agents/langgraph_agents/)
- [domains/healthcare/agents/domain/](../../domains/healthcare/agents/domain/)
