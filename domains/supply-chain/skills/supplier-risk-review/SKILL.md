---
name: supplier-risk-review
description: Evaluate supplier risk signals including single-source dependency, geopolitical exposure, and financial instability. Use when handling workflows related to: supplier_risk_assessment.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: supplier_risk_review
  source_config: agents/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Evaluate supplier risk signals including single-source dependency, geopolitical exposure, and financial instability.

## When To Use
Use when handling workflows related to: supplier_risk_assessment.

## Required Context
- entity_id

## Ontology Dependencies
- entities
- risk_signals

## MCP Tools
- supplier_context_get
- risk_summary_generate

## Runtime Tools
- neo4j

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
