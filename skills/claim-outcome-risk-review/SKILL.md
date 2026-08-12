---
name: claim-outcome-risk-review
description: Analyze claim status and procedure context using claims outcome rules. Use when handling workflows related to: claims_denial_prevention.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: claim_outcome_risk_review
  source_config: rag-api/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Analyze claim status and procedure context using claims outcome rules.

## When To Use
Use when handling workflows related to: claims_denial_prevention.

## Required Context
- question
- patient_id

## Ontology Dependencies
- claims_outcomes
- adverse_outcomes

## MCP Tools
- vector_evidence_search
- patient_context_get
- coding_gap_detect

## Runtime Tools
- qdrant
- neo4j

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
