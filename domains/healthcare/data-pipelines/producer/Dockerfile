FROM ghcr.io/astral-sh/uv:0.12.11 AS uv

FROM python:3.11-slim
WORKDIR /app
COPY domains/healthcare/data-pipelines/producer/pyproject.toml .
RUN --mount=from=uv,source=/uv,target=/usr/local/bin/uv \
	uv pip install --system --no-cache -r pyproject.toml
COPY domains/healthcare/data-pipelines/producer/produce_events.py .
COPY domains/healthcare/data-pipelines/schemas/medical_event.avsc ./schemas/medical_event.avsc
CMD ["python", "produce_events.py"]
