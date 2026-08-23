"""Domain-routed embedding registry.

Maps event types to embedding domains (clinical, claims, device) and loads
a per-domain sentence-transformer model. All domains default to the same
model (EMBEDDING_MODEL env var) unless overridden with EMBEDDING_MODEL_CLINICAL,
EMBEDDING_MODEL_CLAIMS, or EMBEDDING_MODEL_DEVICE.

Falls back to a deterministic MD5 bag-of-words embedding when
sentence-transformers is not installed.
"""
from __future__ import annotations

import hashlib
import os
from typing import Literal


VECTOR_SIZE = 384

EmbeddingDomain = Literal["clinical", "claims", "device"]

EVENT_TYPE_DOMAIN: dict[str, EmbeddingDomain] = {
    "CLINICAL_NOTE": "clinical",
    "LAB_RESULT": "clinical",
    "MEDICATION_ORDER": "clinical",
    "VITAL_SIGN": "device",
    "CLAIM_STATUS": "claims",
}

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

DOMAIN_MODEL_NAMES: dict[EmbeddingDomain, str] = {
    "clinical": os.getenv("EMBEDDING_MODEL_CLINICAL", os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)),
    "claims": os.getenv("EMBEDDING_MODEL_CLAIMS", os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)),
    "device": os.getenv("EMBEDDING_MODEL_DEVICE", os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)),
}

_domain_models: dict[str, object] = {}


def _load_model(model_name: str):
    if model_name in _domain_models:
        return _domain_models[model_name]
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
        print(f"Loaded embedding model: {model_name}")
        _domain_models[model_name] = model
    except Exception:
        print(f"sentence-transformers not available for {model_name}, using MD5 fallback")
        _domain_models[model_name] = False
    return _domain_models[model_name]


def _md5_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def domain_for_event_type(event_type: str) -> EmbeddingDomain:
    return EVENT_TYPE_DOMAIN.get(event_type, "clinical")


def stable_embedding(text: str, dim: int = VECTOR_SIZE, *, domain: EmbeddingDomain = "clinical") -> list[float]:
    model_name = DOMAIN_MODEL_NAMES[domain]
    model = _load_model(model_name)
    if model and model is not False:
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))
    return _md5_embedding(text, dim)


ALL_DOMAINS: list[EmbeddingDomain] = ["clinical", "claims", "device"]
