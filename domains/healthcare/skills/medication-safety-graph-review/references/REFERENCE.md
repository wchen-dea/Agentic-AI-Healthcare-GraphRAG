# medication-safety-graph-review

Source skill id: medication_safety_graph_review

## Business Goals
- medication_safety_review

## Source Mapping
- Flow definition: agents/config/skills_layer.json
- Runtime planner: agents/skills_layer.py
- Runtime endpoint: agents/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: patient_id
- Ontology dependencies: drug_safety, graph_seeds
- MCP tools: patient_context_get, risk_summary_generate, medication_risk_assess
- Runtime tools: neo4j
