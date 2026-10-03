# ADR-0002: Use Qdrant as the streaming vector store

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

Healthcare events stream continuously through Kafka and Flink. The vector store must accept upserts quickly, support metadata filters and keep retrieval latency low enough for live GraphRAG queries.

## Decision

Use Qdrant as the primary vector store for event embeddings. It supports collection-level metadata indexes, ANN search and fast insertion. The Flink pipeline writes embeddings to Qdrant with patient, event and domain metadata so agents can scope retrieval before generation.

## Consequences

Positive:

- Low-latency retrieval for fresh events.
- Payload filtering keeps query scope precise.
- The design is self-hostable and compatible with local Compose workflows.

Trade-offs:

- Collection management and migration are operational work.
- Dense-only query mode is simpler than the original hybrid target.
- Vector dimension changes require re-indexing and a provider switch plan.

## Alternatives Considered

- Pinecone: managed but externalized and less flexible for local-first development.
- pgvector: simpler but weaker for streaming metadata filtering and large-scale ANN workloads.
- Milvus or Weaviate: valid but heavier operational footprint.

## Rollout and Verification

- Provision the collection with the correct dimension and metadata fields.
- Configure the Flink sink to write per-domain vectors and patient filters.
- Validate latency and re-index procedures when moving between local MiniLM and Databricks embeddings.
- Keep collection metadata aligned to the active embedding provider.

## Related

- [ADR-0001](0001-dual-persistence-qdrant-neo4j.md)
- [04_data_platform.md](../04_data_platform.md)
- [08_operation_runbook.md](../08_operation_runbook.md)
- [06_quality_assurance.md](../06_quality_assurance.md)
