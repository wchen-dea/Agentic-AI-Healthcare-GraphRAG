---
name: quality-supplier-scorecard
description: Aggregate quality inspection results by supplier with defect rate trends and corrective action history. Use when handling workflows related to: quality_trend_review.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: quality_supplier_scorecard
  source_config: agents/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Aggregate quality inspection results by supplier with defect rate trends and corrective action history.

## When To Use
Use when handling workflows related to: quality_trend_review.

## Required Context
- entity_id

## Ontology Dependencies
- entities

## MCP Tools
- supplier_context_get
- quality_trend_summarize

## Runtime Tools
- neo4j

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
