---
name: quality-supplier-scorecard
description: Aggregate quality inspection results by supplier with defect rate trends, failure counts, and corrective action tracking.
domain: supply-chain
version: 0.1.0
---

# Quality Supplier Scorecard

## Purpose

Build a quality scorecard for suppliers by aggregating inspection results, defect rates, and corrective action requirements over time.

## When to Use

- Quarterly supplier performance reviews
- Evaluating whether to qualify or disqualify a supplier
- Investigating a spike in defect rates for a specific part
- Audit preparation for incoming quality metrics

## Context Requirements

- `entity_id` — Supplier ID or Part ID

## Graph Traversals

- `(QualityInspection)-[:SUPPLIED_BY]->(Supplier)` — inspections per supplier
- `(QualityInspection)-[:INSPECTED_PART]->(Part)` — inspections per part
- `(QualityInspection)-[:INSPECTED_AT]->(Facility)` — inspection location

## Key Metrics

- Average defect rate per supplier
- Pass/conditional-pass/fail distribution
- Corrective action required count
- Defect category breakdown (dimensional, cosmetic, functional, material)

## MCP Tools

- `supplier_context_get` — supplier graph context with quality history
- `quality_trend_summarize` — narrative summary of quality trends

## Example Queries

- "What is the defect rate trend for supplier-0001?"
- "Which suppliers have the most inspection failures in the last 30 days?"
- "Show corrective action history for parts supplied by Taiwan Semi Components"
