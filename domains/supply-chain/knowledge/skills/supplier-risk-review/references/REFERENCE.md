# supplier-risk-review

Source skill id: supplier_risk_review

## Business Goals

- supplier_risk_assessment

## Source Mapping

- Flow definition: agent-service/src/supply_chain_agent/config/skills_layer.json
- Runtime planner: agent-service/src/supply_chain_agent/tools/skills.py
- Runtime endpoint: agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: entity_id
- Ontology dependencies: entities, risk_signals
- MCP tools: supplier_context_get, risk_summary_generate
- Runtime tools: neo4j
