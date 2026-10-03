# ADR-0011: Use uv workspace packaging and wheel delivery

- Status: accepted
- Date: 2026-09-30
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

The project contains multiple Python packages and service distributions. The build system needs to be deterministic, lightweight and compatible with local development and container builds without depending on editable installs alone.

## Decision

Use uv workspace packaging so packages and domains are resolved consistently. Agent services are built as wheels and installed inside the runtime images, keeping the container build reproducible and aligned with the workspace layout.

## Consequences

Positive:

- Development and production packaging behave more similarly.
- Workspace-level dependency resolution stays controlled.
- Image builds are explicit and easier to reason about.

Trade-offs:

- The team must maintain packaging metadata and build config.
- Wheel-first shipping is stricter than ad hoc local imports.
- Version drift can surface if the workspace and the built image are not updated together.

## Alternatives Considered

- Pure editable installs: simpler locally but less production-accurate.
- Manual pip install scripts: harder to reproduce and review.

## Rollout and Verification

- Register packages in the root `pyproject.toml` and build with uv.
- Build the service as a wheel before image use.
- Run the relevant smoke checks after packaging updates.

## Related

- [03_platform_blueprint.md](../03_platform_blueprint.md)
- [07_cicd_automation.md](../07_cicd_automation.md)
- [ADR-0012](0012-capability-oriented-layout.md)
