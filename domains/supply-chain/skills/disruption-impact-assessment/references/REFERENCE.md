# disruption-impact-assessment

Source skill id: disruption_impact_assessment

## Business Goals

- disruption_impact_analysis

## Source Mapping

- Flow definition: rag-api/src/supply_chain_rag_api/config/skills_layer.json
- Runtime planner: rag-api/src/supply_chain_rag_api/skills_layer.py
- Runtime endpoint: rag-api/src/supply_chain_rag_api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: entities, risk_signals
- MCP tools: disruption_impact_analyze, vector_evidence_search
- Runtime tools: neo4j, qdrant
