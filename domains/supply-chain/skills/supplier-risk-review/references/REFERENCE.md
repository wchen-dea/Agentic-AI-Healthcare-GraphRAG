# supplier-risk-review

Source skill id: supplier_risk_review

## Business Goals
- supplier_risk_assessment

## Source Mapping
- Flow definition: agents/config/skills_layer.json
- Runtime planner: agents/skills_layer.py
- Runtime endpoint: agents/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: entity_id
- Ontology dependencies: entities, risk_signals
- MCP tools: supplier_context_get, risk_summary_generate
- Runtime tools: neo4j
