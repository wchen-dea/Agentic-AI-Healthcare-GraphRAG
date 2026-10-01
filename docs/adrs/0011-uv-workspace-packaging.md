# ADR-0011: uv Workspace Packaging and Wheel-in-Image Delivery

- Status: accepted
- Date: 2026-09-30
- Deciders: platform team
- Supersedes: none
- Superseded by: none

## Context

Both rag-api services (`domains/healthcare/rag-api`, `domains/supply-chain/rag-api`) are pure Python, but they were not packaged:

- Sources sat flat in `rag-api/` and were copied file by file into the image (`COPY app.py`, `COPY domain ./domain`, ...). Forgetting a file broke production only at runtime.
- Imports relied on `sys.path` hacks in code and tests.
- `requirements.txt` held ranges with no lockfile, so CI, local Docker, and production could resolve different versions.
- The healthcare Dockerfile copied `platform/shared` to `/app/shared_lib`, but `retrieval.py` imports `shared.embedding`. The import always failed in the container and fell back silently to the local embedding code (a latent bug).
- `sentence-transformers` pulled the CUDA build of torch on Linux, which made images several GB larger than needed for CPU-only pods.
- Containers ran as root.

## Decision

1. **One uv workspace with one lockfile.** The root `pyproject.toml` declares the members `platform/shared`, `domains/healthcare/rag-api`, and `domains/supply-chain/rag-api`. The root `uv.lock` pins every dependency with hashes for local runs, CI, and images. The root project (`agentic-healthcare`) is the development environment: it depends on every member and on the platform tooling, and has a default `dev` dependency group (pytest, ruff). As a result, `uv sync` and `uv sync --all-packages` produce the same environment, and API pins are declared only in the member `pyproject.toml` files. The members require Python `>=3.11,<3.14`, because `fastapi==0.115.0` and `mcp==1.28.0` do not co-resolve on 3.14+.
2. **Installable packages in a `src/` layout.**

   | Distribution | Import name | Build backend | Location |
   | --- | --- | --- | --- |
   | `healthcare-rag-api` | `healthcare_rag_api` | `uv_build` | `domains/healthcare/rag-api/src/healthcare_rag_api/` |
   | `supply-chain-rag-api` | `supply_chain_rag_api` | `uv_build` | `domains/supply-chain/rag-api/src/supply_chain_rag_api/` |
   | `graphrag-shared` | `shared` | `hatchling` | `platform/shared/` (unchanged on disk) |

   - Imports are package-absolute, for example `from healthcare_rag_api.domain.guardrails import ...`. There are no `sys.path` hacks.
   - Config JSON and fixtures ship as package data. Default config paths resolve relative to the package; relative audit-log paths resolve relative to the working directory.
   - `platform/shared` stays a flat directory because the Flink images `COPY` it as-is. Hatchling remaps it to `shared/` in the wheel. Workspace consumers install it **non-editable**, and `cache-keys` make uv rebuild it when its sources change.
3. **The wheel is the deployable artifact, delivered inside the image.** Kubernetes runs images, not wheels, so each rag-api `Dockerfile` is multi-stage:
   - **builder:** `uv sync --frozen --no-dev --no-install-workspace` installs only locked third-party dependencies into `/opt/venv`. This layer is cached and changes only when `uv.lock` does. Then `uv build --wheel` builds the first-party wheels, and `uv pip install --no-deps` installs them into the venv.
   - **runtime:** a clean `python:3.11-slim` with only `/opt/venv` copied in, the non-root user `app` (uid/gid 10001), and `CMD uvicorn <package>.app:app`.
   - The same Dockerfile serves local Docker Compose, minikube, CI, and EKS. Local Docker and production therefore run the identical wheel set.
4. **CPU-only torch on Linux.** `torch` comes from the explicit `pytorch-cpu` index when `sys_platform == 'linux'`. macOS keeps the PyPI build for development.
5. **Hardened pod defaults.** The Helm chart sets `runAsNonRoot`, uid/gid 10001, the `RuntimeDefault` seccomp profile, `allowPrivilegeEscalation: false`, and drops all capabilities. `readOnlyRootFilesystem` stays off because the Hugging Face cache (`HF_HOME`) and the audit log (`/var/log/rag-api`) are written at runtime.
6. **CI uses uv.** The `rag-api-contracts` workflow uses `astral-sh/setup-uv`, `uv sync --frozen`, and `uv run pytest` for both packages, and builds both images. Changes to `uv.lock`, the root `pyproject.toml`, or `platform/shared/**` trigger it.

## Consequences

### Positive

- Builds are reproducible: CI, local Docker, and production use the same locked dependency set.
- The image installs a wheel, not loose files. A missing module fails the build, not production.
- `shared.embedding` actually loads in the container, which fixes the silent fallback.
- The CPU torch wheel removes the CUDA payload (no `nvidia-*` packages). The healthcare image is about 2.7 GB on arm64, and torch is the largest component.
- Containers run as non-root with least-privilege defaults.

### Negative / trade-offs

- One lock means one version per package for the whole repository. The rag-api pins (for example `fastapi==0.115.0`, `mcp==1.28.0`) also constrain the root dev environment.
- `graphrag-shared` is non-editable. After editing `platform/shared`, run `uv sync` (or `uv sync --reinstall-package graphrag-shared`) before local tests.
- The torch version can differ between macOS (PyPI) and Linux (CPU index). CI and images on Linux are authoritative.
- Docker builds need BuildKit (the default in current Docker) for cache and bind mounts.

## Developer Workflow

```bash
uv sync                       # full dev venv in .venv (same as --all-packages)
make test-hc                  # uv run --package healthcare-rag-api pytest
make test-sc
make build-wheels             # dist/*.whl
docker build -f domains/healthcare/rag-api/Dockerfile -t healthcare-rag-api .
```

Add or upgrade a dependency with `uv add --package healthcare-rag-api <pkg>`, or edit the member `pyproject.toml` and run `uv lock`. Commit `uv.lock` with the change.

## Follow-ups

- Publish wheels to an internal index only if another consumer needs them; today the image is the only consumer.
- Consider `readOnlyRootFilesystem` with `emptyDir` mounts for `HF_HOME` and `/var/log/rag-api`, and pre-bake the embedding model into the image to remove the cold-start download.
- Move the Flink jobs off the `shared_lib` copy to the `graphrag-shared` wheel.
