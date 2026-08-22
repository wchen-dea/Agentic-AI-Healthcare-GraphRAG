# risk-signal-detection

Source skill id: risk_signal_detection

## Business Goals
- clinical_deterioration_triage

## Source Mapping
- Flow definition: agents/config/skills_layer.json
- Runtime planner: agents/skills_layer.py
- Runtime endpoint: agents/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary
- Context requirements: question, patient_id
- Ontology dependencies: lab_signals, drug_safety, claims_outcomes
- MCP tools: vector_evidence_search, risk_summary_generate, timeline_explain, cohort_risk_summary
- Runtime tools: qdrant, neo4j
