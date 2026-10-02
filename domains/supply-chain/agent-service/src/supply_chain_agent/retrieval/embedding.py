"""Query embedding matching the supply-chain ingestion pipeline.

Uses sentence-transformers when installed and falls back to a deterministic
MD5 bag-of-words vector so local runs and tests need no model download.
"""
from __future__ import annotations

import hashlib
import os
from functools import lru_cache
from typing import Any

VECTOR_SIZE = 384
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=2)
def _load_model(model_name: str) -> Any:
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)
    except Exception:
        return None


def _md5_embedding(text: str, dim: int) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        vec[int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16) % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def stable_embedding(text: str, dim: int = VECTOR_SIZE, *, model_name: str | None = None) -> list[float]:
    model = _load_model(model_name or os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL))
    if model is None:
        return _md5_embedding(text, dim)
    vec = model.encode(text, normalize_embeddings=True).tolist()
    return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))
