"""Query embedding matching the supply-chain ingestion pipeline.

Mirrors knowledge_core.embedding (used by the Flink ingest job) so queries and
ingest share one vector space. EMBEDDING_PROVIDER selects the backend:

* ``local`` (default, dev): sentence-transformer baked into the image
  (EMBEDDING_MODEL, default all-MiniLM-L6-v2, 384 dims).
* ``databricks`` (prod): Databricks Model Serving endpoint
  (DATABRICKS_EMBEDDING_ENDPOINT, default databricks-gte-large-en, 1024 dims)
  via DATABRICKS_HOST and DATABRICKS_TOKEN.

EMBEDDING_DIM pins the vector size. Falls back to a deterministic MD5 vector
when the provider is unavailable unless EMBEDDING_REQUIRE_MODEL=true.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import urllib.error
import urllib.request
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DATABRICKS_ENDPOINT = "databricks-gte-large-en"
PROVIDER_DEFAULT_DIMS: dict[str, int] = {"local": 384, "databricks": 1024}


def get_provider() -> str:
    provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower() or "local"
    if provider not in PROVIDER_DEFAULT_DIMS:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER {provider!r}; expected 'local' or 'databricks'")
    return provider


def get_vector_size() -> int:
    override = os.getenv("EMBEDDING_DIM", "").strip()
    if override:
        size = int(override)
        if size <= 0:
            raise ValueError("EMBEDDING_DIM must be a positive integer")
        return size
    return PROVIDER_DEFAULT_DIMS[get_provider()]


VECTOR_SIZE = get_vector_size()


@lru_cache(maxsize=2)
def _load_model(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)
    except Exception:
        return None


def require_model() -> bool:
    return os.getenv("EMBEDDING_REQUIRE_MODEL", "").strip().lower() in {"1", "true", "yes", "on"}


def _md5_embedding(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        vec[int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm else vec


def _databricks_url(endpoint: str) -> str:
    host = os.getenv("DATABRICKS_HOST", "").strip().rstrip("/")
    if not host:
        raise RuntimeError("DATABRICKS_HOST is required when EMBEDDING_PROVIDER=databricks")
    if not host.startswith(("https://", "http://")):
        host = f"https://{host}"
    return f"{host}/serving-endpoints/{endpoint}/invocations"


@lru_cache(maxsize=1024)
def _databricks_embed_cached(endpoint: str, text: str) -> tuple[float, ...]:
    token = os.getenv("DATABRICKS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DATABRICKS_TOKEN is required when EMBEDDING_PROVIDER=databricks")
    request = urllib.request.Request(
        _databricks_url(endpoint),
        data=json.dumps({"input": [text]}).encode("utf-8"),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    timeout = float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30"))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - https endpoint from config
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Databricks embedding endpoint {endpoint!r} returned HTTP {exc.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise RuntimeError(f"Databricks embedding endpoint {endpoint!r} call failed: {type(exc).__name__}") from None
    try:
        vec = [float(x) for x in payload["data"][0]["embedding"]]
    except (KeyError, IndexError, TypeError, ValueError):
        raise RuntimeError(f"Databricks embedding endpoint {endpoint!r} returned an unexpected payload") from None
    return tuple(_l2_normalize(vec))


def databricks_embedding(text: str, dim: int) -> list[float]:
    endpoint = os.getenv("DATABRICKS_EMBEDDING_ENDPOINT", "").strip() or DEFAULT_DATABRICKS_ENDPOINT
    vec = list(_databricks_embed_cached(endpoint, text))
    if len(vec) != dim:
        raise RuntimeError(
            f"Databricks endpoint {endpoint!r} returned {len(vec)} dims but the configured vector size is {dim}; "
            "set EMBEDDING_DIM to match and recreate the Qdrant collections"
        )
    return vec


def stable_embedding(text: str, dim: int | None = None, *, model_name: str | None = None) -> list[float]:
    size = dim or get_vector_size()
    if get_provider() == "databricks":
        try:
            return databricks_embedding(text, size)
        except RuntimeError as exc:
            if require_model():
                raise
            logger.warning("%s; using MD5 fallback", exc)
            return _md5_embedding(text, size)

    resolved = model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)
    model = _load_model(resolved)
    if model is None:
        if require_model():
            raise RuntimeError(
                f"Embedding model {resolved!r} unavailable and EMBEDDING_REQUIRE_MODEL is set; "
                "refusing MD5 fallback so query vectors match ingested vectors"
            )
        return _md5_embedding(text, size)
    vec = model.encode(text, normalize_embeddings=True).tolist()
    return vec[:size] if len(vec) >= size else vec + [0.0] * (size - len(vec))
