---
name: supplier-risk-review
description: Evaluate supplier risk signals including single-source dependency, geopolitical exposure, and financial instability indicators.
domain: supply-chain
version: 0.1.0
---

# Supplier Risk Review

## Purpose

Assess supplier-level risk across concentration, geopolitical, quality, and financial dimensions using graph relationship traversal and vector evidence.

## When to Use

- Evaluating a specific supplier's risk profile before contract renewal
- Identifying single-source dependencies across the supply base
- Screening suppliers in geopolitically sensitive regions
- Reviewing risk signal history for a supplier

## Context Requirements

- `entity_id` — Supplier ID (e.g., `supplier-0001`) or Part ID to find associated suppliers

## Graph Traversals

- `(Supplier)-[:SUPPLIES]->(Part)` — supplier-part coverage
- `(Supplier)-[:HAS_RISK_SIGNAL]->(RiskSignal)` — active risk indicators
- `(Part)-[:DEPENDS_ON*]->(Part)` — BOM cascade for single-source exposure
- `(Supplier)-[:LOCATED_AT]->(Facility)` — geographic risk

## MCP Tools

- `supplier_context_get` — retrieve supplier graph context
- `risk_summary_generate` — generate risk narrative from graph + vector evidence

## Example Queries

- "Which suppliers are single-source for critical parts?"
- "What is the geopolitical risk profile for supplier-0001?"
- "List all tier-1 suppliers with risk scores above 70"
