# grounded-answer

Source skill id: grounded_answer

## Business Goals

- supplier_risk_assessment
- disruption_impact_analysis
- inventory_reorder_planning

## Source Mapping

- Flow definition: agent-service/src/supply_chain_agent/config/skills_layer.json
- Runtime planner: agent-service/src/supply_chain_agent/tools/skills.py
- Runtime endpoint: agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: provenance
- MCP tools: graphrag_answer_generate
- Runtime tools: agent_service, ollama
