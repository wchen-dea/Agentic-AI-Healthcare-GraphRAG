"""Vector and graph retrieval for supply-chain domain."""
from __future__ import annotations

import hashlib
import os
from typing import Any


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
    except Exception:
        _embedding_model = False
    return _embedding_model


def stable_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    model = _get_embedding_model()
    if model and model is not False:
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def vector_search(
    qdrant_client,
    collection: str,
    question: str,
    entity_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    query_vector = stable_embedding(question)
    query_filter = None
    if entity_id:
        query_filter = {"must": [{"key": "entity_id", "match": {"value": entity_id}}]}

    results = qdrant_client.search(
        collection_name=collection,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return [
        {
            "score": result.score,
            "event_id": (result.payload or {}).get("event_id"),
            "entity_id": (result.payload or {}).get("entity_id"),
            "event_type": (result.payload or {}).get("event_type"),
            "text": (result.payload or {}).get("text"),
        }
        for result in results
    ]


_GRAPH_QUERY = """
MATCH (s:Supplier)
WHERE s.id IN $entity_ids
OPTIONAL MATCH (s)-[:SUPPLIES]->(p:Part)
OPTIONAL MATCH (s)-[:HAS_RISK_SIGNAL]->(r:RiskSignal)
OPTIONAL MATCH (p)<-[:CONTAINS_PART]-(a:Assembly)
RETURN s.id AS supplier_id,
       s.name AS name,
       s.country AS country,
       s.risk_tier AS risk_tier,
       collect(DISTINCT {part: p.name, category: p.category})[..20] AS parts,
       collect(DISTINCT {signal: r.type, severity: r.severity, source: r.source})[..10] AS risk_signals
"""


def graph_search(neo4j_driver, entity_ids: list[str]) -> list[dict[str, Any]]:
    with neo4j_driver.session() as session:
        records = session.run(_GRAPH_QUERY, {"entity_ids": entity_ids})
        return [dict(record) for record in records]
