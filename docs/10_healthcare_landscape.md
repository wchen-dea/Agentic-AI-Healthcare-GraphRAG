# 10 — Healthcare Landscape

This document compares the healthcare agent with published reference models for healthcare AI agents and lists the gaps that remain. The implementation it compares against is described in [05 — AI Agents](05_ai_agents.md). Its evaluation coverage is in [06 — Quality Assurance](06_quality_assurance.md). For the business scope, see [01 — Business Requirements](01_business_requirements.md). For the system context, see [02 — Architecture](02_architecture.md).

## 1. Purpose

| Audience | Question this document answers |
| --- | --- |
| Executives | How does the platform compare with leading healthcare agent systems? |
| Architects | Which reference patterns are implemented, which are partial, and which are missing? |
| Engineers | Which modules and interfaces would close each gap? |

Sources:

- Microsoft Research, *Healthcare Agent Orchestrator* (2025)
- Alex G. Lee, healthcare AI agent framework taxonomy (2025)
- PMC survey of healthcare AI agents (2025)

## 2. Industry reference model

### 2.1 Six core modules

| Module | Responsibility | Healthcare-specific requirements |
| --- | --- | --- |
| Perception | Takes in and interprets multimodal clinical data: EHR text, labs, vitals, images and biosignals | Temporal awareness, abnormality detection, cross-source correlation |
| Conversational interface | Natural-language interaction with clinicians and patients | Medical NER, intent classification, evidence-backed answers |
| Interaction | Coordinates agents, clinicians and institutional workflows | Clinician override, feedback capture, explainability, inter-agent handoff |
| Tool integration | Runs tasks against clinical systems such as labs, imaging, EHR and pharmacy | API orchestration, tool-effectiveness tracking, regulatory compliance |
| Memory and learning | Keeps short-term session context and long-term clinical knowledge | Longitudinal patient tracking, personalized recall, privacy-filtered retention |
| Reasoning | Turns inputs and context into clinical decisions | Rule-based and probabilistic inference, uncertainty handling, multi-path reasoning |

### 2.2 Seven agent types

| Agent type | Core capability | Primary modules |
| --- | --- | --- |
| ReAct + RAG | Multi-step reasoning with external knowledge retrieval | Perception, reasoning, tool integration |
| Self-learning | Improves from longitudinal interactions and outcome feedback | Memory, reasoning, perception |
| Memory-enhanced | Continuity of care through patient history | Memory, perception, reasoning |
| LLM-enhanced | Generation, summarization and clinical communication | Conversational, reasoning, perception |
| Tool-enhanced | Orchestrates clinical systems, devices and APIs | Tool integration, interaction, reasoning |
| Self-reflecting | Evaluates and refines its own decisions | Reasoning, memory, interaction |
| Environment-controlling | Controls the physical care environment | Perception, tool integration, memory |

### 2.3 Microsoft Healthcare Agent Orchestrator patterns

| Pattern | Description |
| --- | --- |
| Specialist per modality | Separate agents for radiology, pathology, genomics and structured EHR |
| Orchestrator as facilitator | A central agent runs a structured group chat, assigns tasks, keeps shared context and resolves conflicts |
| Inter-agent communication | Agents pass intermediate results to each other directly, not only through the orchestrator |
| Domain-specific tool planning | Tool calls are planned around clinical workflows rather than generic task chains |
| Verification checkpoints | Agent outputs are checked before other agents use them, so errors don't propagate |
| Composite evaluation | Agent-selection accuracy, intent resolution, contextual relevance, ROUGE precision and factuality |
| Workflow integration | Agents run inside clinical collaboration tools such as Microsoft Teams |

## 3. Module coverage

| Module | Implementation | Coverage |
| --- | --- | --- |
| Perception | Flink enrichment: ontology normalization, lab-signal and drug-safety rules, clinical-text embedding ([04 — Data Platform](04_data_platform.md)) | Strong for structured events and labs. No image or biosignal input. |
| Conversational interface | Provider web UI, `POST /query`, SSE streaming on `POST /query/stream` ([Streaming](05_ai_agents.md#6-streaming)), structured output | Strong. No medical NER and no learned intent classifier; triage is rule-based. |
| Interaction | LangGraph routing, `delegation_router` fan-out to specialists, human review through `interrupt` and `POST /query/resume` ([Memory and human review](05_ai_agents.md#7-memory-and-human-review)) | Partial. A clinician can approve or reject, but agents don't talk to each other directly and feedback is not captured for learning. |
| Tool integration | 10 MCP tools behind role-based `ToolGovernance` with audit events ([MCP tools and skills](05_ai_agents.md#9-mcp-tools-and-skills)) | Strong for internal retrieval and generation. No external EHR, pharmacy or imaging systems. |
| Memory and learning | Session memory with 20 turns and a 3600 s TTL, in-process or Redis | Partial. No longitudinal patient memory and no learning from outcomes. |
| Reasoning | Deterministic graph rules for interactions, contraindications and lab signals; confidence loop; LLM synthesis | Strong for deterministic reasoning. No uncertainty quantification or multi-path probabilistic inference. |

## 4. Agent type mapping

| Agent type | Equivalent in this platform | Status |
| --- | --- | --- |
| ReAct + RAG | LangGraph graph with vector and graph retrieval, plus a confidence loop that re-runs retrieval | Implemented |
| Self-learning | None | Gap |
| Memory-enhanced | Session memory across turns | Partial: session scope only |
| LLM-enhanced | `synthesis` node with provider routing, fallback and model tiers | Implemented |
| Tool-enhanced | MCP tools, the skills layer and the specialist agents | Implemented |
| Self-reflecting | `confidence_evaluator` loop at runtime, plus offline MLflow scorers | Partial: no answer self-critique |
| Environment-controlling | Not applicable | Out of scope |

## 5. Orchestrator pattern comparison

| Pattern | Status in this platform |
| --- | --- |
| Specialist per modality | Partial. There are `medication_safety`, `lab_interpretation` and `coding_review` specialists, but no imaging or genomics agents. |
| Orchestrator as facilitator | Implemented. `triage` plans the work and `delegation_router` sends it to the specialists. |
| Inter-agent communication | Gap. Specialists write to shared graph state and don't exchange messages. |
| Domain-specific tool planning | Implemented. `skills_layer.json` maps business goals to skills and tool chains. |
| Verification checkpoints | Partial. `confidence_evaluator` gates synthesis and optional human review gates release. Specialist outputs are not cross-checked. |
| Composite evaluation | Partial. MLflow has six scorers: routing, agent coverage, evidence completeness, answer quality, safety caveat and latency ([Evaluation gates](06_quality_assurance.md#5-evaluation-gates-and-mlflow-evaluation)). There is no factuality or ROUGE metric. |
| Workflow integration | Gap. Nothing is integrated with Teams, Slack or EHR messaging. |

## 6. Extension roadmap

Streaming, session memory, human review and the confidence loop are already done, so they are not on this list.

### 6.1 Near term

| Priority | Extension | Basis | Approach |
| --- | --- | --- | --- |
| High | Longitudinal patient memory | Memory-enhanced agents | Add a patient-scoped memory store with privacy filtering, next to session memory |
| High | Factuality evaluation | Microsoft factuality metrics | Add a claim-level factuality scorer to the MLflow harness |
| High | Shared HITL checkpointer | Production interaction | Replace `InMemorySaver` with a shared checkpointer so pending reviews survive across replicas |
| Medium | Specialist output verification | Verification checkpoints | Cross-check specialist findings against graph evidence before synthesis |

### 6.2 Medium term

| Priority | Extension | Basis | Approach |
| --- | --- | --- | --- |
| High | Inter-agent communication | Group-chat orchestration | Let specialists exchange intermediate findings before synthesis |
| Medium | Answer self-critique | Self-reflecting agents | Score the draft answer and regenerate it when quality is low |
| Medium | Clinical NER | Perception module | Extract drugs, doses and conditions from notes before embedding |
| Medium | Neural reranking | Retrieval quality | Add a cross-encoder between retrieval and ranking |

### 6.3 Long term

| Priority | Extension | Basis | Approach |
| --- | --- | --- | --- |
| Medium | Multimodal perception | Specialist per modality | Add imaging and pathology agents |
| Medium | Self-learning | Self-learning agents | Use clinician feedback and outcomes to tune retrieval and routing |
| Low | Workflow integration | Teams integration | Embed the agent in clinical collaboration tools |

## Related

- [01 — Business Requirements](01_business_requirements.md)
- [02 — Architecture](02_architecture.md)
- [05 — AI Agents](05_ai_agents.md)
- [06 — Quality Assurance](06_quality_assurance.md)
- [ADR 0007 — LangGraph multi-agent orchestration](adrs/0007-langgraph-multi-agent-orchestration.md)
