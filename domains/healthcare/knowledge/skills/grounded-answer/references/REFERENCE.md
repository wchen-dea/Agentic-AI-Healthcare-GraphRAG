# grounded-answer

Source skill id: grounded_answer

## Business Goals

- clinical_deterioration_triage
- claims_denial_prevention

## Source Mapping

- Flow definition: agent-service/src/healthcare_agent/config/skills_layer.json
- Runtime planner: agent-service/src/healthcare_agent/tools/skills.py
- Runtime endpoint: agent-service/src/healthcare_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question, patient_id
- Ontology dependencies: prompt_policy, provenance
- MCP tools: graphrag_answer_generate
- Runtime tools: agent_service, ollama
