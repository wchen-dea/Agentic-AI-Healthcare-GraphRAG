# claim-outcome-risk-review

Source skill id: claim_outcome_risk_review

## Business Goals
- claims_denial_prevention

## Source Mapping
- Flow definition: rag-api/config/skills_layer.json
- Runtime planner: rag-api/skills_layer.py
- Runtime endpoint: rag-api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: question, patient_id
- Ontology dependencies: claims_outcomes, adverse_outcomes
- MCP tools: vector_evidence_search, patient_context_get, coding_gap_detect
- Runtime tools: qdrant, neo4j
