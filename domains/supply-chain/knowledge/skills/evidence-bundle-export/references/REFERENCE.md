# evidence-bundle-export

Source skill id: evidence_bundle_export

## Business Goals

- quality_trend_review

## Source Mapping

- Flow definition: agent-service/src/supply_chain_agent/config/skills_layer.json
- Runtime planner: agent-service/src/supply_chain_agent/tools/skills.py
- Runtime endpoint: agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: provenance
- MCP tools: evidence_bundle_export
- Runtime tools: agent_service
