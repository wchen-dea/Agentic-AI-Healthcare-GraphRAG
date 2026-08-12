# patient-snapshot

Source skill id: patient_snapshot

## Business Goals
- clinical_deterioration_triage

## Source Mapping
- Flow definition: rag-api/config/skills_layer.json
- Runtime planner: rag-api/skills_layer.py
- Runtime endpoint: rag-api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: patient_id
- Ontology dependencies: entities, relationships
- MCP tools: patient_context_get
- Runtime tools: neo4j
