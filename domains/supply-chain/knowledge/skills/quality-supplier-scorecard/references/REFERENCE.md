# quality-supplier-scorecard

Source skill id: quality_supplier_scorecard

## Business Goals

- quality_trend_review

## Source Mapping

- Flow definition: rag-api/src/supply_chain_rag_api/config/skills_layer.json
- Runtime planner: rag-api/src/supply_chain_rag_api/skills_layer.py
- Runtime endpoint: rag-api/src/supply_chain_rag_api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary

- Context requirements: entity_id
- Ontology dependencies: entities
- MCP tools: supplier_context_get, quality_trend_summarize
- Runtime tools: neo4j
