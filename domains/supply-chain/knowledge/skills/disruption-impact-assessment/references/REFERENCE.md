# disruption-impact-assessment

Source skill id: disruption_impact_assessment

## Business Goals

- disruption_impact_analysis

## Source Mapping

- Flow definition: agent-service/src/supply_chain_agent/config/skills_layer.json
- Runtime planner: agent-service/src/supply_chain_agent/tools/skills.py
- Runtime endpoint: agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: entities, risk_signals
- MCP tools: disruption_impact_assess, vector_evidence_search
- Runtime tools: neo4j, qdrant
