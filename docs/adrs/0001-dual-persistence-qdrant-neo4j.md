# ADR-0001: Use dual persistence (Qdrant + Neo4j)

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The platform needs both semantic retrieval and explicit relationship reasoning. Vector search is ideal for clinical text similarity, while the graph model is needed for patient journeys, drug safety and event lineage. A single store would force trade-offs that limit either semantic recall or causal reasoning.

## Decision

Keep two stores with complementary responsibilities:

| Store | Role |
| --- | --- |
| Neo4j | Graph reasoning, patient journeys, lineage and drug-safety facts |
| Qdrant | Dense vector retrieval over embeddings and metadata filters |

The ingestion pipeline dual-writes each event to both stores, preserving a consistent event identifier and patient scope.

## Consequences

Positive:

- Patient journeys are modeled naturally as graph traversals.
- Drug interaction logic and condition links stay deterministic.
- Semantic retrieval remains fast for unstructured clinical text.

Trade-offs:

- Operational complexity increases because two stores must be monitored and backed up.
- Cross-store consistency is eventually consistent during write windows.
- The team must maintain a disciplined schema and metadata contract.

## Alternatives Considered

- Neo4j-only vector indexing: insufficient ANN performance and metadata filtering for streaming workloads.
- Qdrant-only metadata store: loses graph semantics and patient lineage.
- Relational DB: awkward join paths and poor relationship semantics for clinical graphs.

## Rollout and Verification

- Initialize graph constraints and seed data before serving traffic.
- Verify dual-write smoke tests for patient events and lab results.
- Track sink error rates and alert on divergence or latency regressions.
- Run end-to-end queries against both vector and graph evidence.

## Related

- [02_architecture.md](../02_architecture.md)
- [04_data_platform.md](../04_data_platform.md)
- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0002](0002-qdrant-streaming-vector-store.md)
