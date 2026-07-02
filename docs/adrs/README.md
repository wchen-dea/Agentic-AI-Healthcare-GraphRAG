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

## Related Documentation

| Document | Description |
|----------|-------------|
| [architecture.md](../architecture.md) | System architecture, design patterns, component diagrams |
| [technical_specs.md](../technical_specs.md) | Container inventory, library versions, API specification |
| [business_specs.md](../business_specs.md) | Use cases, business rules, stakeholders |
| [neo4j_model.md](../neo4j_model.md) | Graph model, node labels, relationships, pharmacovigilance |
| [kafka_schema.md](../kafka_schema.md) | Kafka topic topology, Avro schema, payload examples |
| [mcp_layer_design.md](../mcp_layer_design.md) | MCP tool contracts and rollout phases |
| [runbook.md](../runbook.md) | Operations runbook, health checks, failure modes |
| [ai_qa.md](../ai_qa.md) | QA strategy, contract tests, accuracy validation |
