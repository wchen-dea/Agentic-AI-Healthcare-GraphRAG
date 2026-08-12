---
name: grounded-answer
description: Generate a grounded answer with bounded guardrails from vector and graph evidence. Use when handling workflows related to: clinical_deterioration_triage, claims_denial_prevention.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: grounded_answer
  source_config: rag-api/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Generate a grounded answer with bounded guardrails from vector and graph evidence.

## When To Use
Use when handling workflows related to: clinical_deterioration_triage, claims_denial_prevention.

## Required Context
- question
- patient_id

## Ontology Dependencies
- prompt_policy
- provenance

## MCP Tools
- graphrag_answer_generate

## Runtime Tools
- rag_api
- ollama

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
