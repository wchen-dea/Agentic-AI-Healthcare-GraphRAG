# ADR-0012: Use a capability-oriented repository layout

- Status: accepted
- Date: 2026-10-01
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The repository had grown around historical names such as `rag-api`, `healthcare_rag_api` and `platform/shared`. Those names were not aligned with the actual use and created boundary confusion across agents, governance, retrieval and shared infrastructure.

## Decision

Rename the structure around capabilities instead of techniques or vendors. Domains keep business responsibilities and packages hold shared runtime contracts. Folder names such as `orchestration`, `retrieval`, `safety` and `generation` describe the work they do rather than the implementation approach.

## Consequences

Positive:

- The codebase is easier to navigate and review.
- Shared contracts sit in `agent-core` and are reused consistently.
- The layout aligns with ownership boundaries and CI scopes.

Trade-offs:

- Renames are disruptive across imports, CI and docs.
- Historical scripts and wrappers may require a temporary compatibility window.
- Teams need to be disciplined about not reintroducing catch-all folders.

## Alternatives Considered

- Keep the historical names: easier in the short term but weaker long-term maintainability.
- Add more wrappers: hides the real structure and increases confusion.

## Rollout and Verification

- Rename directories with `git mv` and update imports in one pass.
- Keep the package and service names aligned with the new target layout.
- Run tests and validation after the rename to confirm the boundaries do not break runtime behavior.

## Related

- [ADR-0010](0010-layered-agentic-architecture.md)
- [ADR-0011](0011-uv-workspace-packaging.md)
- [02_architecture.md](../02_architecture.md)
