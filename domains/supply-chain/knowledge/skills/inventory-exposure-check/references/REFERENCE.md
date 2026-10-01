# inventory-exposure-check

Source skill id: inventory_exposure_check

## Business Goals

- disruption_impact_analysis
- inventory_reorder_planning

## Source Mapping

- Flow definition: agent-service/src/supply_chain_agent/config/skills_layer.json
- Runtime planner: agent-service/src/supply_chain_agent/tools/skills.py
- Runtime endpoint: agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: entities
- MCP tools: inventory_reorder_check, vector_evidence_search
- Runtime tools: neo4j, qdrant
