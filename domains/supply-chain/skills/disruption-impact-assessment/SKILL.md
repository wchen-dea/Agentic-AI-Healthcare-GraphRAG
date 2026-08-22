---
name: disruption-impact-assessment
description: Trace disruption events through facility and BOM dependency chains to identify affected parts and assemblies. Use when handling workflows related to: disruption_impact_analysis.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: disruption_impact_assessment
  source_config: agents/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Trace disruption events through facility and BOM dependency chains to identify affected parts and assemblies.

## When To Use
Use when handling workflows related to: disruption_impact_analysis.

## Required Context
- question

## Ontology Dependencies
- entities
- risk_signals

## MCP Tools
- disruption_impact_analyze
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
