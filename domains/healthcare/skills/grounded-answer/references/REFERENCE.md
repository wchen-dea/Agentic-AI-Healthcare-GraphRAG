# grounded-answer

Source skill id: grounded_answer

## Business Goals

- clinical_deterioration_triage
- claims_denial_prevention

## Source Mapping

- Flow definition: rag-api/src/healthcare_rag_api/config/skills_layer.json
- Runtime planner: rag-api/src/healthcare_rag_api/skills_layer.py
- Runtime endpoint: rag-api/src/healthcare_rag_api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary

- Context requirements: question, patient_id
- Ontology dependencies: prompt_policy, provenance
- MCP tools: graphrag_answer_generate
- Runtime tools: rag_api, ollama
