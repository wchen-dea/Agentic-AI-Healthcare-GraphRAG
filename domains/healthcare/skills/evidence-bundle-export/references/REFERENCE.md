# evidence-bundle-export

Source skill id: evidence_bundle_export

## Business Goals
- medication_safety_review

## Source Mapping
- Flow definition: rag-api/config/skills_layer.json
- Runtime planner: rag-api/skills_layer.py
- Runtime endpoint: rag-api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: question, patient_id
- Ontology dependencies: provenance, guardrails
- MCP tools: evidence_bundle_export
- Runtime tools: rag_api
