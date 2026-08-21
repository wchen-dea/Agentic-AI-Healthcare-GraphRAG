# Skills Layer

## Purpose

This project now includes an explicit Skills layer that operationalizes the flow:

Business Goals -> Agent -> Skills -> Context -> Ontology -> MCP -> Tools

The standardization and CI validation policy for this layer is formalized in [ADR-0006](adrs/0006-skills-layer-standardization-and-validation.md).

The layer is runtime-backed (not documentation-only):

- Skill catalog and goal mappings are defined in [agents/config/skills_layer.json](../domains/healthcare/agents/config/skills_layer.json).
- Resolution logic is implemented in [agents/skills_layer.py](../domains/healthcare/agents/skills_layer.py).
- LangGraph multi-agent orchestration maps skills to specialized agent nodes in [agents/langgraph_agents/agents.py](../domains/healthcare/agents/langgraph_agents/agents.py).
- Runtime access is exposed through:
  - REST: POST /skills/plan
  - MCP tool: skills_plan_get

## Layer Model

### 1) Business Goals

Business goals are top-level outcomes (for example, clinical triage, medication safety review, claims denial prevention).

Each goal defines:

- description
- default_agent
- ordered list of skill IDs

### 2) Agent

Agent identity is a planner/runtime persona that orchestrates the skill sequence for a goal.

- Default agent comes from goal configuration.
- Caller can override via optional agent field in skills_plan_get.
- In LangGraph mode, the triage agent classifies requests and routes to specialist agents (`medication_safety_agent`, `lab_interpretation_agent`, `coding_review_agent`) based on request type.

### 3) Skills

Each skill describes a reusable unit of capability:

- context_requirements
- ontology_dependencies
- mcp_tools
- runtime_tools

### 4) Context and Ontology

The resolver aggregates:

- union of required context fields
- union of ontology dependencies

This makes prerequisites explicit before tool execution.

### 5) MCP and Tools

The resolver emits:

- mcp_tools: MCP tools expected to be called
- runtime_tools: underlying system tools/services (neo4j, qdrant, rag_api, ollama)

## API Contract

### REST

POST /skills/plan

Request:

```json
{
  "business_goal": "medication_safety_review",
  "agent": "medication_safety_agent"
}
```

Response includes:

- flow
- business_goal
- agent
- skills
- context_requirements
- ontology_dependencies
- mcp_tools
- runtime_tools
- retrieved_at
- trace_id

### MCP

Tool: skills_plan_get

Arguments:

- business_goal (required)
- agent (optional)

## Role and Policy

skills_plan_get is authorized in read_only role via [agents/config/tool_policies.json](../domains/healthcare/agents/config/tool_policies.json).

## Validation

Contracts are tested in [agents/tests/test_contracts.py](../domains/healthcare/agents/tests/test_contracts.py), including:

- successful plan generation for known business goal
- deterministic flow shape and tool outputs
- proper error handling for unknown goals

Agent Skills package compliance is enforced with:

- generator: [scripts/generate_agent_skills.py](../scripts/generate_agent_skills.py)
- validator: [scripts/validate_agent_skills.py](../scripts/validate_agent_skills.py)

CI also includes an optional upstream validation pass using `skills-ref validate`.
The workflow behavior is:

- use `skills-ref` directly when already present on the runner
- otherwise attempt a best-effort on-the-fly install (`python -m pip install --user skills-ref`)
- if install still fails, log a skip message and continue without failing the workflow

Run locally:

```bash
python scripts/generate_agent_skills.py
python scripts/generate_agent_skills.py --check
python scripts/validate_agent_skills.py
```

Generated skill packages are stored under [skills](../domains/healthcare/skills) and include one `SKILL.md` per skill folder plus supporting references.
