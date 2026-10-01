# evidence-bundle-export

Source skill id: evidence_bundle_export

## Business Goals

- medication_safety_review

## Source Mapping

- Flow definition: agent-service/src/healthcare_agent/config/skills_layer.json
- Runtime planner: agent-service/src/healthcare_agent/tools/skills.py
- Runtime endpoint: agent-service/src/healthcare_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question, patient_id
- Ontology dependencies: provenance, guardrails
- MCP tools: evidence_bundle_export
- Runtime tools: rag_api
