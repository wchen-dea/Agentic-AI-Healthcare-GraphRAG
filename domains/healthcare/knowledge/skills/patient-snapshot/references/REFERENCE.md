# patient-snapshot

Source skill id: patient_snapshot

## Business Goals

- clinical_deterioration_triage

## Source Mapping

- Flow definition: agent-service/src/healthcare_agent/config/skills_layer.json
- Runtime planner: agent-service/src/healthcare_agent/tools/skills.py
- Runtime endpoint: agent-service/src/healthcare_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: patient_id
- Ontology dependencies: entities, relationships
- MCP tools: patient_context_get
- Runtime tools: neo4j
