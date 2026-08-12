# ADR-0004: Skills Layer Standardization and Validation

- Status: accepted
- Date: 2026-06-12
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The repository now exposes an explicit skills planning flow across REST and MCP surfaces:

- REST: `POST /skills/plan`
- MCP: `skills_plan_get`

The project also generates skill packages under `skills/` from a central source of truth.
Without a formal decision, three risks emerge:

1. Runtime skills behavior can drift from generated skill package artifacts.
2. CI can pass while skills metadata contracts silently regress.
3. MCP tool catalog evolution can diverge from documented Business Goal -> Agent -> Skills flow.

The architecture needs one authoritative format and validation policy that is enforced in both local development and CI.

## Decision

Adopt a standardized Skills layer with generator-plus-validator enforcement.

1. Canonical source of truth for planning remains `rag-api/config/skills_layer.json`.
2. Runtime resolution remains in `rag-api/skills_layer.py` and is exposed by:
   - `POST /skills/plan`
   - `skills_plan_get`
3. Generated skill package artifacts under `skills/` are maintained by `scripts/generate_agent_skills.py`.
4. Structural validation is enforced by `scripts/validate_agent_skills.py`.
5. CI enforces both checks in a dedicated skills validation job.
6. Upstream `skills-ref validate` is optional and non-blocking:
   - use it when available,
   - attempt best-effort install when missing,
   - skip gracefully when still unavailable.

## Consequences

Positive:

- Skills planning contracts are explicit, testable, and reproducible.
- Runtime behavior and generated skills artifacts remain synchronized.
- CI catches schema drift before merge.
- The project can consume stricter upstream tooling when available without adding fragility.

Trade-offs:

- Additional scripts and CI steps increase maintenance surface.
- Optional upstream validation is not guaranteed on every runner.
- Contributors must regenerate artifacts when skills config changes.

## Alternatives Considered

- Runtime-only skills with no generated artifacts:
  - rejected because external consumers and documentation lose a stable package format.
- Manual curation of `skills/*/SKILL.md` files:
  - rejected due to high drift risk and review burden.
- Require `skills-ref` as a hard CI dependency:
  - rejected because availability differs by runner environment and would create unnecessary pipeline failures.

## Rollout and Verification

1. Maintain planner source in `rag-api/config/skills_layer.json`.
2. Generate artifacts with `python scripts/generate_agent_skills.py`.
3. Validate artifacts with `python scripts/validate_agent_skills.py`.
4. Enforce generator `--check` plus validator in CI.
5. Run optional upstream `skills-ref validate` with best-effort install and graceful skip.
6. Verify contract behavior through `rag-api/tests/test_contracts.py` coverage for skills plan resolution.

## Related

- [ADR-0005: Embed FastMCP in rag-api](./0005-embed-fastmcp-in-rag-api.md)
- [Skills Layer](../skills_layer.md)
- [MCP Layer Design](../mcp_layer_design.md)
- [Technical Specs](../technical_specs.md)
- [AI QA](../ai_qa.md)