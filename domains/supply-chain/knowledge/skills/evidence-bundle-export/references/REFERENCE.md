# evidence-bundle-export

Source skill id: evidence_bundle_export

## Business Goals

- quality_trend_review

## Source Mapping

- Flow definition: rag-api/src/supply_chain_rag_api/config/skills_layer.json
- Runtime planner: rag-api/src/supply_chain_rag_api/skills_layer.py
- Runtime endpoint: rag-api/src/supply_chain_rag_api/app.py (/skills/plan and skills_plan_get)

## Tool and Context Summary

- Context requirements: question
- Ontology dependencies: provenance
- MCP tools: evidence_bundle_export
- Runtime tools: rag_api
