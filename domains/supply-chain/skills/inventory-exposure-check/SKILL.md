---
name: inventory-exposure-check
description: Identify parts below reorder points, low days-of-supply, and at-risk facility-part positions. Use when handling workflows related to: disruption_impact_analysis, inventory_reorder_planning.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: inventory_exposure_check
  source_config: agents/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Identify parts below reorder points, low days-of-supply, and at-risk facility-part positions.

## When To Use
Use when handling workflows related to: disruption_impact_analysis, inventory_reorder_planning.

## Required Context
- question

## Ontology Dependencies
- entities

## MCP Tools
- inventory_status_get
- vector_evidence_search

## Runtime Tools
- neo4j
- qdrant

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
