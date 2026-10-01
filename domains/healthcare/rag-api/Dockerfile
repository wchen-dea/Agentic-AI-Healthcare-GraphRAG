# syntax=docker/dockerfile:1.7
# Build context: repository root. Same image for local Docker and Kubernetes.
# See docs/adrs/0011-uv-workspace-packaging.md.

ARG PYTHON_IMAGE=python:3.11-slim

# --- builder: resolve locked deps, build wheel(s), install into /opt/venv ----
FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.12.11 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /src

# Third-party dependencies only (cached layer; changes only when uv.lock does).
# Every workspace member's pyproject.toml is needed for workspace discovery.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=platform/shared/pyproject.toml,target=platform/shared/pyproject.toml \
    --mount=type=bind,source=domains/healthcare/rag-api/pyproject.toml,target=domains/healthcare/rag-api/pyproject.toml \
    --mount=type=bind,source=domains/supply-chain/rag-api/pyproject.toml,target=domains/supply-chain/rag-api/pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace --package healthcare-rag-api

# First-party code: build wheel(s) from the workspace and install them (no deps;
# the locked dependency set is already in /opt/venv).
COPY uv.lock pyproject.toml ./
COPY platform/shared/pyproject.toml platform/shared/pyproject.toml
COPY domains/healthcare/rag-api/pyproject.toml domains/healthcare/rag-api/pyproject.toml
COPY domains/supply-chain/rag-api/pyproject.toml domains/supply-chain/rag-api/pyproject.toml
COPY platform/shared/__init__.py platform/shared/embedding.py platform/shared/ontology_loader.py \
     platform/shared/rules_engine.py platform/shared/runner.py platform/shared/storage.py \
     platform/shared/
COPY platform/shared/ontology platform/shared/ontology
COPY domains/healthcare/rag-api/src domains/healthcare/rag-api/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv build --wheel --package graphrag-shared --out-dir /dist && \
    uv build --wheel --package healthcare-rag-api --out-dir /dist && \
    uv pip install --python /opt/venv/bin/python --no-deps /dist/*.whl

# --- runtime: slim base + venv only, non-root ---------------------------------
FROM ${PYTHON_IMAGE} AS runtime
RUN groupadd --system --gid 10001 app && \
    useradd --system --uid 10001 --gid app --create-home --home-dir /home/app app && \
    mkdir -p /app /var/log/rag-api && chown app:app /app /var/log/rag-api
COPY --from=builder /opt/venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/home/app/.cache/huggingface \
    RAG_API_AUDIT_LOG_PATH=/var/log/rag-api/audit.log
WORKDIR /app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "healthcare_rag_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
