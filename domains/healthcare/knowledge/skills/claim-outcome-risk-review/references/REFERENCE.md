# claim-outcome-risk-review

Source skill id: claim_outcome_risk_review

## Business Goals

- claims_denial_prevention

## Source Mapping

- Flow definition: agent-service/src/healthcare_agent/config/skills_layer.json
- Runtime planner: agent-service/src/healthcare_agent/tools/skills.py
- Runtime endpoint: agent-service/src/healthcare_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question, patient_id
- Ontology dependencies: claims_outcomes, adverse_outcomes
- MCP tools: vector_evidence_search, patient_context_get, coding_gap_detect
- Runtime tools: qdrant, neo4j
