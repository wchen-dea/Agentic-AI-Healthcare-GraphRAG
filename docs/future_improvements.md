# Future Improvements Backlog

## Purpose

This document tracks execution backlog items and staged work that remain after current implementation milestones.

Use [target_architecture.md](target_architecture.md) for strategic architecture and capability intent.
Use this file for delivery planning, prioritization, and completion tracking.

## Current Status Summary

Completed or largely implemented:

- Stage 0 documentation and baseline architecture references,
- ontology configuration, ontology loader, and rule-pack integration in Flink modules,
- shared rag-api domain package (`domain/models.py`, `domain/planner.py`, `domain/evidence.py`),
- planner-driven query orchestration with deterministic ranking and planner metadata,
- expanded MCP tools (`timeline_explain`, `medication_risk_assess`, `coding_gap_detect`, `cohort_risk_summary`),
- planner quality suites (`test_planner_evaluation.py`, `test_planner_edge_cases.py`),
- provider adapter abstraction with Ollama runtime adapter.

Partially implemented:

- terminology governance breadth and mapping coverage,
- ontology conformance and retrieval quality benchmark depth,
- provider abstraction breadth (single provider implementation today),
- production privacy, policy, and rollout controls.

## Remaining High-Priority Backlog

### 1. Complete Stage 4 evaluation hardening

Target outcomes:

- add retrieval benchmark suites with stable datasets and release-over-release comparison,
- add grounded answer scorecards and failure taxonomy,
- expand ontology conformance depth beyond current checks,
- add quality trend reporting in CI artifacts.

Suggested repo touchpoints:

- `rag-api/tests/`
- `docs/ai_qa.md`
- `.github/workflows/rag-api-contracts.yml`
- `.github/workflows/ontology-conformance.yml`

### 2. Expand provider adapter implementations

Target outcomes:

- add additional provider adapters behind the existing abstraction,
- keep retrieval orchestration unchanged across provider swaps,
- add adapter-focused contract tests and fallback behavior tests.

Suggested repo touchpoints:

- `rag-api/llm_provider.py`
- `rag-api/app.py`
- `rag-api/tests/test_contracts.py`

### 3. Finish terminology and ontology governance depth

Target outcomes:

- widen standard-code mapping coverage and validation,
- strengthen governance workflow for mapping updates,
- ensure graph seed and runtime semantic consistency remains auditable.

Suggested repo touchpoints:

- `config/ontology/`
- `scripts/generate_ontology_seed_cypher.py`
- `scripts/validate_ontology.py`
- `neo4j/generated_ontology_seeds.cypher`

### 4. Production controls for non-demo readiness (Stage 5)

Target outcomes:

- stronger policy classes and PHI handling boundaries,
- retention and lineage controls tied to ontology provenance,
- deployment-level rollout and rollback playbooks,
- explicit SLO gates for latency, freshness, and audit completeness.

Suggested repo touchpoints:

- `deploy/production/`
- `docs/runbook.md`
- `docs/technical_specs.md`
- monitoring and alerting assets

## Staged Plan Status

| Stage | Focus | Status | Notes |
| --- | --- | --- | --- |
| Stage 0 | Documentation and semantic contract baseline | Completed | Architecture, ADRs, and references are in place. |
| Stage 1 | Ontology externalization and normalization | Largely completed | Loader/normalization/rules modules exist; continue mapping depth work. |
| Stage 2 | Query planner and evidence ranking | Completed (baseline) | Planner and ranking shipped with fixture and edge-case suites. |
| Stage 3 | Skill-composed MCP expansion | Completed (current scope) | Expanded tools and policy updates shipped; continue iterative refinement as needed. |
| Stage 4 | Evaluation hardening and provider abstraction | In progress | Planner tests and provider abstraction started; benchmark/scorecard/provider breadth still open. |
| Stage 5 | Production controls for real data readiness | Pending | Requires policy/privacy/SLO rollout controls for non-demo operation. |

## Near-Term Execution Order

1. Stage 4 retrieval and grounding benchmark suites.
2. Stage 4 additional provider adapters and adapter-level tests.
3. Stage 1 terminology/ontology mapping coverage deepening.
4. Stage 5 production privacy and rollout controls.
