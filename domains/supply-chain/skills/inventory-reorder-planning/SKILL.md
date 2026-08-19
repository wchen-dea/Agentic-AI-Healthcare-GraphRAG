---
name: inventory-reorder-planning
description: Identify parts below reorder points, low days-of-supply positions, and facility-level inventory exposure for reorder prioritization.
domain: supply-chain
version: 0.1.0
---

# Inventory Reorder Planning

## Purpose

Surface inventory positions that are at or below reorder thresholds, prioritize reorder actions by criticality and days-of-supply, and correlate with active disruptions that may affect replenishment.

## When to Use

- Daily inventory review for reorder triggers
- Pre-disruption inventory exposure assessment
- Warehouse capacity planning and allocation review

## Context Requirements

- `question` — inventory query (optionally scoped by facility or part)

## Graph Traversals

- `(Facility)-[inv:HOLDS_INVENTORY]->(Part)` — current stock levels
- `inv.below_reorder` — boolean flag for threshold breach
- `inv.days_of_supply` — urgency indicator
- `(Part)-[:DEPENDS_ON]->(Part)` — cascade impact if a component runs out
- `(Facility)-[:DISRUPTED_BY]->(DisruptionEvent)` — replenishment risk

## MCP Tools

- `inventory_status_get` — retrieve inventory positions with reorder flags
- `vector_evidence_search` — find recent PO/shipment events for affected parts

## Example Queries

- "Which parts are below reorder point at facility-004?"
- "Show all facility-part positions with fewer than 5 days of supply"
- "Are any below-reorder parts also affected by active disruptions?"
