---
name: disruption-impact-analysis
description: Trace active disruptions through facility and BOM dependency chains to identify affected parts, assemblies, and downstream impact.
domain: supply-chain
version: 0.1.0
---

# Disruption Impact Analysis

## Purpose

When a disruption event occurs (factory shutdown, port closure, natural disaster), trace the impact through the supply chain graph to identify all affected parts, dependent assemblies, and at-risk facilities.

## When to Use

- A facility reports an operational disruption
- Natural disaster or geopolitical event affects a region
- Assessing cascade risk from a single-point-of-failure supplier or facility

## Context Requirements

- `question` — description of the disruption scenario or facility ID

## Graph Traversals

- `(Facility)-[:DISRUPTED_BY]->(DisruptionEvent)` — active disruptions
- `(DisruptionEvent)-[:AFFECTS_PART]->(Part)` — directly affected parts
- `(Part)<-[:DEPENDS_ON*]-(Part)` — upstream BOM cascade (which assemblies use this part)
- `(Supplier)-[:SUPPLIES]->(Part)` — alternative supplier availability
- `(Facility)-[inv:HOLDS_INVENTORY]->(Part)` — buffer stock availability

## MCP Tools

- `disruption_impact_analyze` — trace disruption cascade
- `vector_evidence_search` — find related disruption events in vector store

## Example Queries

- "If facility-001 shuts down, which parts and assemblies are affected?"
- "What is the estimated duration and mitigation status of active disruptions?"
- "Are there alternative suppliers for parts affected by the Shanghai port closure?"
