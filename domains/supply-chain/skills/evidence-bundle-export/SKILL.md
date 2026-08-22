---
name: evidence-bundle-export
description: Export evidence bundle for traceability, review, and audit workflows. Use when handling workflows related to: quality_trend_review.
license: Apache-2.0
compatibility: Designed for Agent Skills-compatible coding agents with MCP support
metadata:
  source_skill_id: evidence_bundle_export
  source_config: agents/config/skills_layer.json
  generator: scripts/generate_agent_skills.py
---

## Overview
Export evidence bundle for traceability, review, and audit workflows.

## When To Use
Use when handling workflows related to: quality_trend_review.

## Required Context
- question

## Ontology Dependencies
- provenance

## MCP Tools
- evidence_bundle_export

## Runtime Tools
- rag_api

## Procedure
1. Validate required context inputs are present.
2. Resolve ontology prerequisites before tool invocation.
3. Invoke listed MCP tools in the order that best fits the user request.
4. Return an evidence-grounded response and capture guardrail metadata.

## References
See references/REFERENCE.md for source mapping and runtime notes.
