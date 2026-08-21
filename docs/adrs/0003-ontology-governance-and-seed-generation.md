# ADR-0003: Ontology Governance and Seed Generation

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The repository now uses explicit ontology artifacts to drive ingestion semantics, graph seed generation, and validation:

- Ontology configuration under `domains/healthcare/config/ontology/`
- Generated seed artifact `domains/healthcare/neo4j/generated_ontology_seeds.cypher`
- Bootstrap runner `domains/healthcare/neo4j/bootstrap.sh`
- Validation checks in `scripts/validate_ontology.py`

Without a formal governance decision, the stack can drift in several ways:

1. Ontology config changes can diverge from generated Neo4j seed Cypher.
2. Runtime rule behavior can drift from declared ontology relationships.
3. CI can miss semantic contract regressions when only code-level tests pass.

The project needs an explicit decision for source-of-truth ownership, regeneration policy, and CI enforcement.

## Decision

Adopt ontology-first governance with generated seed artifacts and conformance validation.

1. `domains/healthcare/config/ontology/` is the canonical source of truth for ontology and rule semantics.
2. `domains/healthcare/neo4j/generated_ontology_seeds.cypher` is a generated artifact and must be regenerated from ontology config when ontology changes.
3. `domains/healthcare/neo4j/init.cypher` remains focused on constraints and bootstrap orchestration, not hand-maintained semantic seed content.
4. Seed generation is performed by `scripts/generate_ontology_seed_cypher.py`.
5. Conformance validation is enforced by `scripts/validate_ontology.py`, including:
   - generated seed freshness checks,
   - bootstrap verification,
   - focused ontology/runtime unit test suites.
6. CI must run ontology conformance checks for relevant changes before merge.

## Consequences

Positive:

- Ontology semantics are declared once and propagated consistently.
- Seed artifacts are reproducible and reviewable.
- Semantic drift is detected early in CI.
- Runtime behavior and graph bootstrap remain aligned.

Trade-offs:

- Contributors must regenerate artifacts when ontology config changes.
- CI gains additional runtime and dependency requirements.
- Generated artifact diffs must be reviewed carefully to catch unintended semantic changes.

## Alternatives Considered

- Keep ontology definitions only in hand-written Cypher:
  - rejected due to high drift risk and weak testability.
- Runtime-only ontology with no generated seed artifact:
  - rejected because bootstrap reproducibility and reviewability degrade.
- Optional validation only (no CI gate):
  - rejected because semantic regressions can bypass review under fast iteration.

## Rollout and Verification

1. Modify ontology and rule configs under `domains/healthcare/config/ontology/`.
2. Regenerate seed artifact with `python scripts/generate_ontology_seed_cypher.py`.
3. Run conformance checks with `python scripts/validate_ontology.py`.
4. Confirm bootstrap behavior using `python scripts/test_neo4j_bootstrap.py` when ontology-affecting changes are made.
5. Enforce CI conformance gate in `.github/workflows/ontology-conformance.yml`.

## Related

- [ADR-0001: Use dual persistence (Qdrant + Neo4j)](./0001-dual-persistence-qdrant-neo4j.md)
- [ADR-0006: Skills layer standardization and validation](./0006-skills-layer-standardization-and-validation.md)
- [Target Architecture](../target_architecture.md)
- [Technical Specs](../technical_specs.md)
- [Runbook](../runbook.md)