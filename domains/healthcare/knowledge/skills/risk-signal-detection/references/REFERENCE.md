# risk-signal-detection

Source skill id: risk_signal_detection

## Business Goals

- clinical_deterioration_triage

## Source Mapping

- Flow definition: agent-service/src/healthcare_agent/config/skills_layer.json
- Runtime planner: agent-service/src/healthcare_agent/tools/skills.py
- Runtime endpoint: agent-service/src/healthcare_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question, patient_id
- Ontology dependencies: lab_signals, drug_safety, claims_outcomes
- MCP tools: vector_evidence_search, risk_summary_generate, timeline_explain, cohort_risk_summary
- Runtime tools: qdrant, neo4j
