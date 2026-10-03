"""Domain-routed, provider-pluggable embedding registry.

Ingest (Flink) and query (agents) must embed with the same provider, model and
dimension. The provider is selected with EMBEDDING_PROVIDER:

* ``local`` (default, dev): a sentence-transformer baked into the Flink and
  agent images (EMBEDDING_MODEL, default all-MiniLM-L6-v2, 384 dims). Each
  domain may override the model with EMBEDDING_MODEL_CLINICAL/_CLAIMS/_DEVICE.
* ``databricks`` (prod): a Databricks Model Serving embedding endpoint
  (DATABRICKS_EMBEDDING_ENDPOINT, default databricks-gte-large-en, 1024 dims)
  called over HTTPS with DATABRICKS_HOST and DATABRICKS_TOKEN.

The vector size defaults per provider and can be pinned with EMBEDDING_DIM.
Switching provider or model changes the vector space, so Qdrant collections
must be recreated and re-ingested.

When the provider is unavailable the module falls back to a deterministic MD5
bag-of-words vector. Set EMBEDDING_REQUIRE_MODEL=true (as the images do) to
raise instead of silently writing or querying incompatible vectors.
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
from typing import Literal

logger = logging.getLogger(__name__)

EmbeddingDomain = Literal["clinical", "claims", "device"]
EmbeddingProvider = Literal["local", "databricks"]

EVENT_TYPE_DOMAIN: dict[str, EmbeddingDomain] = {
    "CLINICAL_NOTE": "clinical",
    "LAB_RESULT": "clinical",
    "MEDICATION_ORDER": "clinical",
    "VITAL_SIGN": "device",
    "CLAIM_STATUS": "claims",
}

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_DATABRICKS_ENDPOINT = "databricks-gte-large-en"
PROVIDER_DEFAULT_DIMS: dict[str, int] = {"local": 384, "databricks": 1024}

DOMAIN_MODEL_NAMES: dict[EmbeddingDomain, str] = {
    "clinical": os.getenv("EMBEDDING_MODEL_CLINICAL", os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)),
    "claims": os.getenv("EMBEDDING_MODEL_CLAIMS", os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)),
    "device": os.getenv("EMBEDDING_MODEL_DEVICE", os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)),
}

_domain_models: dict[str, object] = {}


def get_provider() -> EmbeddingProvider:
    provider = os.getenv("EMBEDDING_PROVIDER", "local").strip().lower() or "local"
    if provider not in PROVIDER_DEFAULT_DIMS:
        raise ValueError(f"Unsupported EMBEDDING_PROVIDER {provider!r}; expected 'local' or 'databricks'")
    return provider  # type: ignore[return-value]


def get_vector_size() -> int:
    override = os.getenv("EMBEDDING_DIM", "").strip()
    if override:
        size = int(override)
        if size <= 0:
            raise ValueError("EMBEDDING_DIM must be a positive integer")
        return size
    return PROVIDER_DEFAULT_DIMS[get_provider()]


# Resolved once at import so ingest jobs can size Qdrant collections.
VECTOR_SIZE = get_vector_size()


def require_model() -> bool:
    return os.getenv("EMBEDDING_REQUIRE_MODEL", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_model(model_name: str):
    if model_name in _domain_models:
        return _domain_models[model_name]
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        logger.info("Loaded embedding model: %s", model_name)
        _domain_models[model_name] = model
    except Exception:
        logger.warning("sentence-transformers not available for %s, using MD5 fallback", model_name)
        _domain_models[model_name] = False
    return _domain_models[model_name]


def _md5_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
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


@lru_cache(maxsize=4096)
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


def domain_for_event_type(event_type: str) -> EmbeddingDomain:
    return EVENT_TYPE_DOMAIN.get(event_type, "clinical")


def _fit(vec: list[float], dim: int) -> list[float]:
    return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))


def stable_embedding(text: str, dim: int | None = None, *, domain: EmbeddingDomain = "clinical") -> list[float]:
    size = dim or get_vector_size()
    if get_provider() == "databricks":
        try:
            return databricks_embedding(text, size)
        except RuntimeError as exc:
            if require_model():
                raise
            logger.warning("%s; using MD5 fallback", exc)
            return _md5_embedding(text, size)

    model_name = DOMAIN_MODEL_NAMES[domain]
    model = _load_model(model_name)
    if model and model is not False:
        return _fit(model.encode(text, normalize_embeddings=True).tolist(), size)
    if require_model():
        raise RuntimeError(
            f"Embedding model {model_name!r} unavailable and EMBEDDING_REQUIRE_MODEL is set; "
            "refusing MD5 fallback so ingest and query vectors stay compatible"
        )
    return _md5_embedding(text, size)


ALL_DOMAINS: list[EmbeddingDomain] = ["clinical", "claims", "device"]
