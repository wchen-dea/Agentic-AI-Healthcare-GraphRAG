---
name: risk-signal-detection
description: Detect risk signals from vector evidence and graph patterns. Use when handling workflows related to: clinical_deterioration_triage.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: risk_signal_detection
  source_config: agents/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Detect risk signals from vector evidence and graph patterns.

## When To Use
Use when handling workflows related to: clinical_deterioration_triage.

## Required Context
- question
- patient_id

## Ontology Dependencies
- lab_signals
- drug_safety
- claims_outcomes

## MCP Tools
- vector_evidence_search
- risk_summary_generate
- timeline_explain
- cohort_risk_summary

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
