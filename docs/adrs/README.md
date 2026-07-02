# Architecture Decision Records

This folder contains Architecture Decision Records (ADRs) for the project.

## ADR Index

| # | Title | Layer | Status |
|---|-------|-------|--------|
| [Template](0000-template.md) | ADR template | — | — |
| [ADR-0001](0001-dual-persistence-qdrant-neo4j.md) | Use dual persistence (Qdrant + Neo4j) | Data architecture | accepted |
| [ADR-0002](0002-qdrant-streaming-vector-store.md) | Qdrant as the streaming vector store for real-time RAG | Data — vector store | accepted |
| [ADR-0003](0003-local-first-llm-provider-routing.md) | Local-first LLM with provider routing | AI generation | accepted (partial) |
| [ADR-0004](0004-embed-fastmcp-in-rag-api.md) | Embed FastMCP in rag-api | API surface | accepted |

## Conventions

- Numbering is sequential and immutable.
- Status values: proposed, accepted, superseded, deprecated.
- Update impacted docs when an ADR is accepted or superseded.
