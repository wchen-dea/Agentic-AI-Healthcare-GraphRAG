from __future__ import annotations

import hashlib
import os


VECTOR_SIZE = 384
_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
        print(f"Loaded neural embedding model: {_EMBEDDING_MODEL_NAME}")
    except Exception:
        _embedding_model = False
        print("sentence-transformers not available, using deterministic MD5 embedding")
    return _embedding_model


def _md5_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def stable_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    model = _get_embedding_model()
    if model and model is not False:
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))
    return _md5_embedding(text, dim)
