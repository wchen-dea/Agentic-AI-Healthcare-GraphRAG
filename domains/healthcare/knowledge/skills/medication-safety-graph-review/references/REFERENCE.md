# medication-safety-graph-review

Source skill id: medication_safety_graph_review

## Business Goals

- medication_safety_review

## Source Mapping

- Flow definition: agent-service/src/healthcare_agent/config/skills_layer.json
- Runtime planner: agent-service/src/healthcare_agent/tools/skills.py
- Runtime endpoint: agent-service/src/healthcare_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: patient_id
- Ontology dependencies: drug_safety, graph_seeds
- MCP tools: patient_context_get, risk_summary_generate, medication_risk_assess
- Runtime tools: neo4j
