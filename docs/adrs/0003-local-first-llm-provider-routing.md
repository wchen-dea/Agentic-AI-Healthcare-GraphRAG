# ADR-0003: Local-first LLM with provider routing

- Status: accepted (partially implemented)
- Date: 2026-06-26

## Context

Local development should run without external dependencies, while production should support managed model providers.

## Decision

Adopt local-first generation with provider abstraction:

- Default local provider: Ollama.
- Production-ready routing path: Anthropic or OpenAI adapters.
- Keep retrieval orchestration stable and swap provider client behind adapter.

Implementation status in this repository today:

- Implemented: local Ollama-first runtime in `rag-api/app.py`.
- Planned extension: provider adapter and environment-based routing for Anthropic/OpenAI.

## Consequences

Positive:

- Fast local onboarding and offline-friendly development.
- Clear migration path to production model providers.

Trade-offs:

- Provider behavior differences require adapter and testing discipline.
- Model/version drift can affect output consistency.

## Related

- [Architecture](../architecture.md)
- [MCP Layer Design](../mcp_layer_design.md)
