# grounded-answer

Source skill id: grounded_answer

## Business Goals
- supplier_risk_assessment
- disruption_impact_analysis
- inventory_reorder_planning

## Source Mapping
- Flow definition: agents/config/skills_layer.json
- Runtime planner: agents/skills_layer.py
- Runtime endpoint: agents/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: question
- Ontology dependencies: provenance
- MCP tools: graphrag_answer_generate
- Runtime tools: rag_api, ollama
