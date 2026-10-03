# Architecture Decision Records

This directory records the main technical choices behind the GraphRAG platform. The ADRs are ordered by sequence and reflect the implementation as it evolved from prototype to shared workspace.

## ADR index

| # | Title | Status | Date |
| --- | --- | --- | --- |
| [0000-template](0000-template.md) | ADR template | template | — |
| [0001](0001-dual-persistence-qdrant-neo4j.md) | Dual persistence with Qdrant and Neo4j | accepted | 2026-06-12 |
| [0002](0002-qdrant-streaming-vector-store.md) | Qdrant as the streaming vector store | accepted | 2026-06-12 |
| [0003](0003-ontology-governance-and-seed-generation.md) | Ontology governance and seed generation | accepted | 2026-06-12 |
| [0004](0004-local-first-llm-provider-routing.md) | Local-first LLM provider routing | accepted | 2026-06-12 |
| [0005](0005-embed-fastmcp-in-rag-api.md) | Embed FastMCP in the RAG API | accepted | 2026-06-12 |
| [0006](0006-skills-layer-standardization-and-validation.md) | Skills layer standardization and validation | accepted | 2026-06-12 |
| [0007](0007-langgraph-multi-agent-orchestration.md) | LangGraph multi-agent orchestration | accepted | 2026-06-12 |
| [0008](0008-mlflow-tracing-and-evaluation.md) | MLflow tracing and evaluation | accepted | 2026-06-12 |
| [0009](0009-domain-module-extraction.md) | Domain module extraction | accepted | 2026-06-12 |
| [0010](0010-layered-agentic-architecture.md) | Layered agentic architecture | accepted | 2026-09-30 |
| [0011](0011-uv-workspace-packaging.md) | uv workspace packaging | accepted | 2026-09-30 |
| [0012](0012-capability-oriented-layout.md) | Capability-oriented layout and shared agent core | accepted | 2026-10-01 |

## Related docs

- [../02_architecture.md](../02_architecture.md)
- [../05_ai_agents.md](../05_ai_agents.md)
- [../06_quality_assurance.md](../06_quality_assurance.md)
- [../08_operation_runbook.md](../08_operation_runbook.md)
