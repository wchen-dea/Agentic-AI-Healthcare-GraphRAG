# inventory-exposure-check

Source skill id: inventory_exposure_check

## Business Goals

- disruption_impact_analysis
- inventory_reorder_planning

## Source Mapping

- Flow definition: rag-api/src/supply_chain_rag_api/config/skills_layer.json
- Runtime planner: rag-api/src/supply_chain_rag_api/skills_layer.py
- Runtime endpoint: rag-api/src/supply_chain_rag_api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: entities
- MCP tools: inventory_status_get, vector_evidence_search
- Runtime tools: neo4j, qdrant
