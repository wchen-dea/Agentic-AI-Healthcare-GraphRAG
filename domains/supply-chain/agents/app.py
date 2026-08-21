"""Supply Chain GraphRAG API — FastAPI + embedded FastMCP."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Supply Chain GraphRAG API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6335")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "supplychain_events")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "supplychain123")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
VECTOR_SIZE = 384
SKILLS_LAYER_PATH = os.getenv("SC_SKILLS_LAYER_PATH", "config/skills_layer.json")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "300"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1200"))

# ── Lazy clients ──────────────────────────────────────────────────────────────

_neo4j_driver = None
_qdrant_client = None
_skills_layer = None


def _neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        from neo4j import GraphDatabase
        _neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _neo4j_driver


def _qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(url=QDRANT_URL)
    return _qdrant_client


def _skills():
    global _skills_layer
    if _skills_layer is None:
        from skills_layer import load_skills_layer
        _skills_layer = load_skills_layer(SKILLS_LAYER_PATH)
    return _skills_layer


# ── Embedding ─────────────────────────────────────────────────────────────────

_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
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
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


# ── LLM provider ──────────────────────────────────────────────────────────────

from llm_provider import create_provider

llm_provider = create_provider("ollama", base_url=OLLAMA_URL, configured_model=OLLAMA_MODEL)


# ── Domain planner ────────────────────────────────────────────────────────────

from domain.planner import classify_request_type, select_retrieval_plan


# ── Retrieval ─────────────────────────────────────────────────────────────────

def vector_context(question: str, entity_id: str | None, limit: int) -> list[dict]:
    qvec = stable_embedding(question)
    query_filter = None
    if entity_id:
        query_filter = {"should": [
            {"key": "entity_id", "match": {"value": entity_id}},
            {"key": "supplier_id", "match": {"value": entity_id}},
            {"key": "facility_id", "match": {"value": entity_id}},
        ]}
    results = _qdrant().search(collection_name=QDRANT_COLLECTION, query_vector=qvec, query_filter=query_filter, limit=limit)
    return [{"score": hit.score, "event_id": hit.payload.get("event_id"), "entity_id": hit.payload.get("entity_id"),
             "event_type": hit.payload.get("event_type"), "text": hit.payload.get("text")} for hit in results]


def graph_context(entity_ids: list[str]) -> list[dict]:
    with _neo4j().session() as session:
        records = session.run("""
            UNWIND $ids AS eid
            OPTIONAL MATCH (s:Supplier {id: eid})
            OPTIONAL MATCH (p:Part {id: eid})
            OPTIONAL MATCH (f:Facility {id: eid})
            WITH coalesce(s, p, f) AS entity, eid
            WHERE entity IS NOT NULL

            CALL (entity) {
                OPTIONAL MATCH (entity)-[:SUPPLIES]->(part:Part)
                RETURN collect(DISTINCT {part_id: part.id, name: part.name, criticality: part.criticality})[..10] AS supplied_parts
            }
            CALL (entity) {
                OPTIONAL MATCH (entity)-[:HAS_RISK_SIGNAL]->(r:RiskSignal)
                RETURN collect(DISTINCT {category: r.category, description: r.description})[..10] AS risk_signals
            }
            CALL (entity) {
                OPTIONAL MATCH (entity)-[:DISRUPTED_BY]->(d:DisruptionEvent)
                RETURN collect(DISTINCT {type: d.disruption_type, severity: d.severity, duration_days: d.estimated_duration_days, mitigation: d.mitigation_status})[..10] AS disruptions
            }
            CALL (entity) {
                OPTIONAL MATCH (qi:QualityInspection)-[:SUPPLIED_BY]->(entity)
                WITH qi WHERE qi IS NOT NULL
                RETURN collect(DISTINCT {result: qi.result, defect_rate: qi.defect_rate, part_id: qi.part_id})[..10] AS quality_inspections
            }
            CALL (entity) {
                OPTIONAL MATCH (entity)-[inv:HOLDS_INVENTORY]->(part:Part)
                RETURN collect(DISTINCT {part_id: part.id, on_hand: inv.on_hand_qty, below_reorder: inv.below_reorder, days_of_supply: inv.days_of_supply})[..10] AS inventory
            }

            RETURN eid AS entity_id, labels(entity)[0] AS entity_type,
                   entity.name AS name, entity.country AS country, entity.region AS region,
                   entity.risk_score AS risk_score, entity.geopolitical_risk AS geo_risk,
                   entity.criticality AS criticality, entity.facility_type AS facility_type,
                   supplied_parts, risk_signals, disruptions, quality_inspections, inventory
        """, {"ids": entity_ids})
        return [dict(r) for r in records]


# ── Query ─────────────────────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    entity_id: str | None = None


def _ts():
    return datetime.now(timezone.utc).isoformat()


def _compact_context(items: list[dict]) -> str:
    return json.dumps(items, default=str)[:4000] if items else "(none)"


def ask_llm(question: str, vec_ctx: list[dict], graph_ctx: list[dict]) -> str:
    prompt = f"""You are a supply-chain analytics RAG assistant for synthetic demo data only.
Summarize the evidence and answer the question.

Question:
{question}

Vector context from Qdrant:
{_compact_context(vec_ctx)}

Graph context from Neo4j:
{_compact_context(graph_ctx)}

Answer with:
1. Key findings
2. Relationship-based reasoning
3. Evidence snippets
4. Caveats
"""
    return llm_provider.generate(
        prompt=prompt,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        max_tokens=LLM_MAX_TOKENS,
        temperature=0.2,
    )


def run_query(question: str, entity_id: str | None) -> dict:
    request_type = classify_request_type(question, entity_id)
    plan = select_retrieval_plan(request_type, question, entity_id, max_top_k=5)
    vec_ctx = vector_context(plan.query_text, entity_id, plan.top_k)
    entity_ids = list({v.get("entity_id") for v in vec_ctx if v.get("entity_id")} | ({entity_id} if entity_id else set()))
    graph_ctx = graph_context(entity_ids) if entity_ids else []
    answer = ask_llm(question, vec_ctx, graph_ctx)
    return {
        "question": question,
        "request_type": request_type,
        "retrieval_plan": {"name": plan.name, "top_k": plan.top_k, "reason": plan.reason},
        "entities": entity_ids,
        "vector_context": vec_ctx,
        "graph_context": graph_ctx,
        "answer": answer,
        "retrieved_at": _ts(),
        "trace_id": str(uuid.uuid4()),
    }


@app.get("/health")
def health():
    return {"status": "ok", "domain": "supply-chain"}


@app.post("/query")
def query_endpoint(req: QueryRequest):
    result = run_query(req.question, req.entity_id)
    for v in result.get("vector_context", []):
        v.pop("text", None)
        v["text_redacted"] = True
    return result


# ── Skills plan endpoint ──────────────────────────────────────────────────────

class SkillsPlanRequest(BaseModel):
    business_goal: str


@app.post("/skills/plan")
def skills_plan(req: SkillsPlanRequest):
    from skills_layer import build_skill_plan, SkillsLayerError
    try:
        return build_skill_plan(_skills(), business_goal=req.business_goal)
    except SkillsLayerError as e:
        raise HTTPException(status_code=400, detail=str(e))
