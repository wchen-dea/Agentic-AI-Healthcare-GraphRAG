# grounded-answer

Source skill id: grounded_answer

## Business Goals

- supplier_risk_assessment
- disruption_impact_analysis
- inventory_reorder_planning

## Source Mapping

- Flow definition: rag-api/src/supply_chain_rag_api/config/skills_layer.json
- Runtime planner: rag-api/src/supply_chain_rag_api/skills_layer.py
- Runtime endpoint: rag-api/src/supply_chain_rag_api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: provenance
- MCP tools: graphrag_answer_generate
- Runtime tools: rag_api, ollama
