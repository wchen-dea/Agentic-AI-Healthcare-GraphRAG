---
name: medication-safety-graph-review
description: Review active medications against contraindications, known reactions, and interaction mechanisms. Use when handling workflows related to: medication_safety_review.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: medication_safety_graph_review
  source_config: rag-api/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Review active medications against contraindications, known reactions, and interaction mechanisms.

## When To Use
Use when handling workflows related to: medication_safety_review.

## Required Context
- patient_id

## Ontology Dependencies
- drug_safety
- graph_seeds

## MCP Tools
- patient_context_get
- risk_summary_generate
- medication_risk_assess

## Runtime Tools
- neo4j

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
