# ADR-0003: Adopt ontology governance and seed generation

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The graph must stay interpretable and consistent across healthcare and supply-chain domains. Without explicit governance, edges drift, labels become ambiguous and seed data becomes inconsistent with production queries.

## Decision

Define a small, governed ontology for core entities and relationships. Seed data includes reference nodes and deterministic edges such as medication interactions, contraindications and lab signals. The ontology and seed material are treated as versioned assets that are validated in CI.

## Consequences

Positive:

- Graph semantics stay explicit and auditable.
- New domains can reuse the same entity and relationship patterns.
- Seed data reduces the need for ad hoc graph creation at runtime.

Trade-offs:

- The ontology requires governance and version control.
- New entities must be added deliberately rather than as free-form graph growth.
- Over-standardization can slow the addition of niche domain concepts.

## Alternatives Considered

- Free-form graph creation: easier at first but low consistency and poor query quality.
- Pure document-only retrieval: simpler but loses causal and lineage-aware reasoning.

## Rollout and Verification

- Validate ontology definitions and graph constraints as part of stack validation.
- Seed the relationship tables and reference nodes during bootstrap.
- Check for broken labels or missing reference data before release.
- Review domain-specific additions in pull requests.

## Related

- [04_data_platform.md](../04_data_platform.md)
- [05_ai_agents.md](../05_ai_agents.md)
- [ADR-0001](0001-dual-persistence-qdrant-neo4j.md)
