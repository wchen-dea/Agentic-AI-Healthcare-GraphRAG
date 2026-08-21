# ADR-0004: Local-First LLM with Provider Routing

- Status: accepted (partial)
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

Local development should run without external dependencies, while production should support managed model providers.

## Decision

Adopt local-first generation with provider abstraction:

- Default local provider: Ollama.
- Production-ready routing path: Anthropic or OpenAI adapters.
- Keep retrieval orchestration stable and swap provider client behind adapter.

Implementation status:

- Implemented: `OllamaProvider` in `domains/healthcare/rag-api/llm_provider.py` with `create_provider()` factory.
- Prompt construction and synthesis extracted into `domains/healthcare/rag-api/domain/synthesis.py`.
- Roadmap: additional provider adapters and environment-based routing for Anthropic/OpenAI.

## Consequences

Positive:

- Fast local onboarding and offline-friendly development.
- Clear migration path to production model providers.
- Provider abstraction decouples retrieval orchestration from generation backend.

Trade-offs:

- Provider behavior differences require adapter and testing discipline.
- Model/version drift can affect output consistency.
- Only Ollama is implemented at runtime today; `create_provider()` rejects other provider names.

## Alternatives Considered

- Direct Ollama calls without abstraction: rejected because it couples retrieval logic to a specific provider, making future provider additions invasive.
- LangChain LLM abstraction: rejected to avoid adding LangChain as a runtime dependency for generation when a lightweight adapter is sufficient.

## Rollout and Verification

- Set `OLLAMA_MODEL` and `OLLAMA_URL` in `.env`.
- Verify model availability: `docker exec -it infra-ollama ollama list`
- Test generation: `curl -s -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"test","patient_id":"patient-0001"}' | jq .answer`

## Related

- [Architecture](../architecture.md)
- [MCP Layer Design](../mcp_layer_design.md)
- [Skills Layer](../skills_layer.md)
