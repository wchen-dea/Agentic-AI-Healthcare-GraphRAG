# grounded-answer

Source skill id: grounded_answer

## Business Goals
- clinical_deterioration_triage
- claims_denial_prevention

## Source Mapping
- Flow definition: rag-api/config/skills_layer.json
- Runtime planner: rag-api/skills_layer.py
- Runtime endpoint: rag-api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: question, patient_id
- Ontology dependencies: prompt_policy, provenance
- MCP tools: graphrag_answer_generate
- Runtime tools: rag_api, ollama
