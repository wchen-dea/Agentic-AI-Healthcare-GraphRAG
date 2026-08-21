# ADR-0009: Domain Module Extraction for rag-api

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The healthcare rag-api `app.py` grew to 1,410 lines containing configuration, external client setup, embedding logic, retrieval queries (including a 120-line Neo4j Cypher query), prompt construction, LLM synthesis, response sanitization, budget enforcement, HTTP routes, and MCP tools. The LangGraph agent nodes imported retrieval and synthesis functions from `app.py` at runtime, creating a circular dependency chain (`app` → `langgraph_agents` → `agents` → `app`).

This made it difficult to:

- test domain logic without constructing the full FastAPI application,
- import retrieval or synthesis from scripts or notebooks without triggering client initialization,
- reason about which module owns which responsibility.

## Decision

Extract pure domain logic from `app.py` into focused modules under `domain/`:

| Module | Responsibility | Extracted from |
| --- | --- | --- |
| `domain/retrieval.py` | Embedding, vector search (Qdrant), graph search (Neo4j Cypher) | `stable_embedding`, `vector_context`, `graph_context` |
| `domain/synthesis.py` | Prompt construction, context compaction, LLM synthesis | `_compact_vector_context`, `_compact_graph_context`, `ask_ollama` |
| `domain/response_policy.py` | Truncation, sanitization, budget enforcement, confidence estimation | `_truncate_text`, `_sanitize_*`, `_apply_response_budget`, `_estimate_confidence` |

`app.py` becomes a composition root: settings, client initialization, thin wrappers that inject clients into domain functions, HTTP routes, and MCP tools.

Domain functions accept clients as parameters rather than importing module-level globals, enabling dependency injection for testing.

## Consequences

Positive:

- `app.py` reduced from 1,410 to 1,047 lines (–26%).
- Domain logic is testable without FastAPI, Qdrant, or Neo4j clients.
- LangGraph agents and the ReAct controller can import domain modules without triggering app initialization.
- Duplicated confidence estimation consolidated into `response_policy.estimate_confidence`.
- Duplicated evaluation scorers consolidated: `mlflow_eval.py` delegates to `evaluation.py`.

Trade-offs:

- LangGraph agent nodes still use deferred `from app import` for `vector_context` and `graph_context` wrappers that inject the live clients. This is a runtime dependency, not a circular import.
- Adding a new retrieval source requires updating both `domain/retrieval.py` and the thin wrapper in `app.py`.

## Alternatives Considered

- Full dependency injection container: rejected as over-engineering for the current module count.
- Move all logic into `domain/` and make `app.py` purely HTTP: rejected because MCP tool handlers contain business-specific projection logic that doesn't fit cleanly into domain modules.

## Rollout and Verification

- All 97 existing tests pass without modification.
- `python -m pytest domains/healthcare/agents/tests/ --tb=line` confirms no regressions.
- Docker build includes the new modules via `COPY domain ./domain` in the Dockerfile.

## Related

- [ADR-0007: LangGraph multi-agent query orchestration](./0007-langgraph-multi-agent-orchestration.md)
- [domains/healthcare/agents/domain/](../../domains/healthcare/agents/domain/)
