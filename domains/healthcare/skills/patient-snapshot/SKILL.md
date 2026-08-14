---
name: patient-snapshot
description: Retrieve patient graph context with core conditions, symptoms, observations, medications, and vitals. Use when handling workflows related to: clinical_deterioration_triage.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: patient_snapshot
  source_config: rag-api/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Retrieve patient graph context with core conditions, symptoms, observations, medications, and vitals.

## When To Use
Use when handling workflows related to: clinical_deterioration_triage.

## Required Context
- patient_id

## Ontology Dependencies
- entities
- relationships

## MCP Tools
- patient_context_get

## Runtime Tools
- neo4j

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
