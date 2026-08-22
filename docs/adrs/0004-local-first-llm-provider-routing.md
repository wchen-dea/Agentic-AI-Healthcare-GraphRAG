# ADR-0004: Local-First LLM with Provider Routing

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

Local development should run without external dependencies, while production should support managed model providers.

## Decision

Adopt local-first generation with provider abstraction:

- Default local provider: Ollama.
- Production providers: OpenAI (primary) with Anthropic (fallback).
- Keep retrieval orchestration stable and swap provider client behind adapter.

Implementation status:

- Implemented: `OllamaProvider`, `OpenAIProvider`, `AnthropicProvider`, `FallbackProvider` in `domains/healthcare/agents/llm_provider.py`.
- Factory: `create_provider()` routes by `LLM_PROVIDER` env var.
- Fallback: `FallbackProvider` wraps primary + fallback; triggered by `LLM_FALLBACK_PROVIDER` env var.
- Prompt construction and synthesis extracted into `domains/healthcare/agents/domain/synthesis.py`.
- Helm values: dev uses Ollama, production uses OpenAI + Anthropic fallback.

## Consequences

Positive:

- Fast local onboarding and offline-friendly development.
- Clear migration path to production model providers.
- Provider abstraction decouples retrieval orchestration from generation backend.

Trade-offs:

- Provider behavior differences require adapter and testing discipline.
- Model/version drift can affect output consistency.
- Fallback adds latency on primary failure.

## Alternatives Considered

- Direct Ollama calls without abstraction: rejected because it couples retrieval logic to a specific provider, making future provider additions invasive.
- LangChain LLM abstraction: rejected to avoid adding LangChain as a runtime dependency for generation when a lightweight adapter is sufficient.

## Rollout and Verification

- Set `OLLAMA_MODEL` and `OLLAMA_URL` in `.env`.
- Verify model availability: `docker exec -it infra-ollama ollama list`
- Test generation: `curl -s -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{"question":"test","patient_id":"patient-0001"}' | jq .answer`

## Related

- [Architecture](../02_architecture.md)
- [MCP Layer Design](../07_mcp_layer_design.md)
- [Skills Layer](../08_skills_layer.md)
