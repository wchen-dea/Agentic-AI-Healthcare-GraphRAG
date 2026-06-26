import hashlib
import os
from contextlib import asynccontextmanager

import requests
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "healthcare_events")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "healthcare123")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
VECTOR_SIZE = 384
MCP_SERVER_NAME = os.getenv("MCP_SERVER_NAME", "HealthcareGraphRAG MCP")

mcp = FastMCP(MCP_SERVER_NAME)
mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="Healthcare Hybrid GraphRAG API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
qdrant = QdrantClient(url=QDRANT_URL)
neo4j = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))


class QueryRequest(BaseModel):
    question: str
    patient_id: str | None = None


def run_query(question: str, patient_id: str | None = None) -> dict:
    vctx = vector_context(question, patient_id)
    patient_ids = list({item["patient_id"] for item in vctx if item.get("patient_id")})
    if patient_id:
        patient_ids = list(set(patient_ids + [patient_id]))
    gctx = graph_context(patient_ids) if patient_ids else []
    answer = ask_ollama(question, vctx, gctx)
    return {
        "question": question,
        "patients": patient_ids,
        "vector_context": vctx,
        "graph_context": gctx,
        "answer": answer,
    }


def stable_embedding(text: str, dim: int = VECTOR_SIZE):
    vec = [0.0] * dim
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def vector_context(question: str, patient_id: str | None):
    query_vector = stable_embedding(question)
    qfilter = None
    if patient_id:
        qfilter = {"must": [{"key": "patient_id", "match": {"value": patient_id}}]}

    results = qdrant.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=query_vector,
        query_filter=qfilter,
        limit=5,
    )
    return [
        {
            "score": r.score,
            "event_id": r.payload.get("event_id"),
            "patient_id": r.payload.get("patient_id"),
            "event_type": r.payload.get("event_type"),
            "text": r.payload.get("text"),
        }
        for r in results
    ]


def graph_context(patient_ids):
    with neo4j.session() as session:
        records = session.run(
            """
            MATCH (p:Patient)
            WHERE p.id IN $patient_ids
            OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
            OPTIONAL MATCH (p)-[:HAS_SYMPTOM]->(s:Symptom)
            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
            OPTIONAL MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
            OPTIONAL MATCH (m)-[i:INTERACTS_WITH]->(m2:Medication)
            OPTIONAL MATCH (p)-[:HAS_DEVICE_READING]->(dr:DeviceReading)
            OPTIONAL MATCH (p)-[:HAS_CLAIM]->(cl:Claim)
            RETURN p.id AS patient_id,
                   collect(DISTINCT c.name) AS conditions,
                   collect(DISTINCT s.name) AS symptoms,
                   collect(DISTINCT {name: o.name, value: o.value, unit: o.unit, abnormal: o.abnormal}) AS observations,
                   collect(DISTINCT {medication: m.name, dose: mo.dose, frequency: mo.frequency}) AS medications,
                   collect(DISTINCT {from: m.name, to: m2.name, risk: i.risk, severity: i.severity}) AS interactions,
                   collect(DISTINCT {heart_rate: dr.heart_rate, spo2: dr.spo2, bp: dr.systolic_bp + '/' + dr.diastolic_bp}) AS vitals,
                   collect(DISTINCT {payer: cl.payer, code: cl.procedure_code, status: cl.status}) AS claims
            """,
            {"patient_ids": patient_ids},
        )
        return [dict(r) for r in records]


def _model_base_name(model_name: str) -> str:
    return model_name.split(":", 1)[0]


def _available_ollama_models() -> list[str]:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=10)
        if response.status_code != 200:
            return []
        models = response.json().get("models", [])
        return [m.get("name") for m in models if m.get("name")]
    except Exception:
        return []


def _resolve_ollama_model() -> tuple[str | None, list[str]]:
    configured = (OLLAMA_MODEL or "").strip()
    available = _available_ollama_models()

    if not configured:
        return (available[0], available) if available else (None, [])

    if configured in available:
        return configured, available

    configured_base = _model_base_name(configured)
    for name in available:
        if _model_base_name(name) == configured_base:
            return name, available

    if available:
        return available[0], available

    return None, []


def ask_ollama(question, vector_ctx, graph_ctx):
    prompt = f"""
You are a clinical decision-support RAG assistant for synthetic demo data only.
Do not provide final medical advice. Summarize likely context and evidence.

Question:
{question}

Vector context from Qdrant:
{vector_ctx}

Graph context from Neo4j:
{graph_ctx}

Answer with:
1. Key findings
2. Relationship-based reasoning
3. Evidence snippets
4. Safety caveat
"""
    selected_model, available_models = _resolve_ollama_model()
    if not selected_model:
        return (
            "LLM error: no Ollama models are installed. "
            "Pull one with: docker exec -it healthcare-ollama ollama pull llama3.1"
        )

    response = requests.post(
        f"{OLLAMA_URL}/api/generate",
        json={"model": selected_model, "prompt": prompt, "stream": False},
        timeout=120,
    )
    if response.status_code != 200:
        body = response.text
        if "not found" in body.lower():
            available_msg = ", ".join(available_models) if available_models else "none"
            return (
                f"LLM error: requested model '{selected_model}' was not found. "
                f"Configured model: '{OLLAMA_MODEL}'. Available models: {available_msg}. "
                "Pull a model with: docker exec -it healthcare-ollama ollama pull llama3.1"
            )
        return f"LLM error: {body}"
    return response.json().get("response")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/mcp/health")
def mcp_health():
    return {
        "status": "ok",
        "mcp": {
            "enabled": True,
            "transport": "streamable-http",
            "endpoint": "/mcp",
            "note": "Diagnostic route only; use /mcp for MCP protocol traffic.",
        },
    }


@app.get("/")
def root():
    return RedirectResponse(url="/docs", status_code=307)


@app.get("/favicon.ico")
def favicon():
    # Return an empty icon response to avoid noisy 404s in browser logs.
    return Response(status_code=204)


@app.post("/query")
def query(req: QueryRequest):
    return run_query(req.question, req.patient_id)


@mcp.tool()
def patient_context_get(
    patient_id: str,
    include_claims: bool = True,
    include_interactions: bool = True,
) -> dict:
    result = run_query("Return patient graph context for review.", patient_id)
    graph_ctx = result.get("graph_context", [])

    if not include_claims:
        for item in graph_ctx:
            item.pop("claims", None)
    if not include_interactions:
        for item in graph_ctx:
            item.pop("interactions", None)

    return {
        "patient_id": patient_id,
        "graph_context": graph_ctx,
    }


@mcp.tool()
def vector_evidence_search(
    question: str,
    patient_id: str | None = None,
    top_k: int = 5,
) -> dict:
    result = run_query(question, patient_id)
    return {
        "question": question,
        "vector_context": result.get("vector_context", [])[:top_k],
    }


@mcp.tool()
def graphrag_answer_generate(
    question: str,
    patient_id: str | None = None,
    response_style: str = "concise",
) -> dict:
    style_prefix = {
        "concise": "Answer concisely. ",
        "clinical": "Use clinically oriented language. ",
        "audit": "Include evidence traceability details. ",
    }
    merged_question = style_prefix.get(response_style, "") + question
    result = run_query(merged_question, patient_id)
    return {
        "answer": result.get("answer", ""),
        "patients": result.get("patients", []),
        "vector_context": result.get("vector_context", []),
        "graph_context": result.get("graph_context", []),
    }


@mcp.tool()
def risk_summary_generate(
    patient_id: str,
    time_window_hours: int = 72,
) -> dict:
    prompt = (
        f"Generate a risk summary for patient {patient_id} "
        f"over the last {time_window_hours} hours using available evidence."
    )
    result = run_query(prompt, patient_id)
    risk_signals = []
    for item in result.get("vector_context", []):
        event_type = item.get("event_type")
        if event_type and event_type not in risk_signals:
            risk_signals.append(event_type)

    return {
        "patient_id": patient_id,
        "summary": result.get("answer", ""),
        "risk_signals": risk_signals,
    }


@mcp.tool()
def evidence_bundle_export(
    question: str,
    patient_id: str | None = None,
    include_raw_payload: bool = False,
) -> dict:
    result = run_query(question, patient_id)
    bundle = {
        "question": question,
        "patients": result.get("patients", []),
        "vector_context": result.get("vector_context", []),
        "graph_context": result.get("graph_context", []),
        "answer": result.get("answer", ""),
    }
    if not include_raw_payload:
        for item in bundle["vector_context"]:
            item.pop("text", None)
    return bundle


# Mount MCP as a fallback ASGI app so /mcp is served by the AI API process.
app.mount("/", mcp_http_app)
