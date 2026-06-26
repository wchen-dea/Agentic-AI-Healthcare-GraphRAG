# ADR-0002: Use dual persistence (Qdrant + Neo4j)

- Status: accepted
- Date: 2026-06-26

## Context

The system needs both semantic retrieval and explicit relationship reasoning for healthcare evidence.

## Decision

Use two stores with distinct roles:

- Qdrant for vector similarity retrieval.
- Neo4j for relationship-rich graph context.

Flink writes to both stores after event enrichment.

## Consequences

Positive:

- Better grounding quality by combining semantic and graph evidence.
- Clear separation between similarity search and lineage/relationship queries.

Trade-offs:

- Additional operational complexity (two data systems).
- Need for consistency checks between dual sinks.

## Related

- [Architecture](../ARCHITECTURE.md)
- [Neo4j Model](../NEO4J_MODEL.md)
