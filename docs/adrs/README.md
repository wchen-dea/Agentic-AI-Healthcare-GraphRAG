# Architecture Decision Records

This folder contains Architecture Decision Records (ADRs) for the project.

## ADR Index

| # | Title | Layer | Status |
| --- | --- | --- | --- |
| [Template](0000-template.md) | ADR template | — | — |
| [ADR-0001](0001-dual-persistence-qdrant-neo4j.md) | Dual persistence (Qdrant + Neo4j) | Data architecture | accepted |
| [ADR-0002](0002-qdrant-streaming-vector-store.md) | Qdrant as the streaming vector store for real-time RAG | Data — vector store | accepted |
| [ADR-0003](0003-ontology-governance-and-seed-generation.md) | Ontology governance and seed generation | Semantic model governance | accepted |
| [ADR-0004](0004-local-first-llm-provider-routing.md) | Local-first LLM with provider routing | AI generation | accepted |
| [ADR-0005](0005-embed-fastmcp-in-rag-api.md) | Embed FastMCP in rag-api | API surface | accepted |
| [ADR-0006](0006-skills-layer-standardization-and-validation.md) | Skills layer standardization and validation | Agent orchestration and CI policy | accepted |
| [ADR-0007](0007-langgraph-multi-agent-orchestration.md) | LangGraph multi-agent query orchestration | Agent orchestration | accepted |
| [ADR-0008](0008-mlflow-tracing-and-evaluation.md) | MLflow tracing and evaluation for agent pipelines | Observability | accepted |
| [ADR-0009](0009-domain-module-extraction.md) | Domain module extraction for rag-api | Code architecture | accepted |

## Conventions

- Numbering is sequential and immutable.
- ADR index ordering follows numeric ADR sequence and is expected to align with AI system design and build-logic procedure order.
- Status values: proposed, accepted, superseded, deprecated.
- Update impacted docs when an ADR is accepted or superseded.

## Related Documentation

| Document | Description |
| --- | --- |
| [02_architecture.md](../02_architecture.md) | System architecture, design patterns, component diagrams |
| [03_target_architecture.md](../03_target_architecture.md) | Reference architecture, target outcomes, and capability map |
| [14_future_improvements.md](../14_future_improvements.md) | Actionable backlog, staged delivery plan, and execution sequence |
| [06_technical_specs.md](../06_technical_specs.md) | Container inventory, library versions, API specification |
| [01_business_specs.md](../01_business_specs.md) | Use cases, business rules, stakeholders |
| [05_neo4j_model.md](../05_neo4j_model.md) | Graph model, node labels, relationships, pharmacovigilance |
| [04_kafka_schema.md](../04_kafka_schema.md) | Kafka topic topology, Avro schema, payload examples |
| [07_mcp_layer_design.md](../07_mcp_layer_design.md) | MCP tool contracts and rollout stages |
| [08_skills_layer.md](../08_skills_layer.md) | Skills layer flow, generated package model, and validation |
| [13_runbook.md](../13_runbook.md) | Operations runbook, health checks, failure modes |
| [12_ai_qa.md](../12_ai_qa.md) | QA strategy, contract tests, accuracy validation |
