# quality-supplier-scorecard

Source skill id: quality_supplier_scorecard

## Business Goals

- quality_trend_review

## Source Mapping

- Flow definition: agent-service/src/supply_chain_agent/config/skills_layer.json
- Runtime planner: agent-service/src/supply_chain_agent/tools/skills.py
- Runtime endpoint: agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: entity_id
- Ontology dependencies: entities
- MCP tools: supplier_context_get, graphrag_answer_generate
- Runtime tools: neo4j
