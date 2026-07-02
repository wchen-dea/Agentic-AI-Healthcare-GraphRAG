from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import requests
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from qdrant_client import QdrantClient


def _to_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    values = [item.strip() for item in value.split(",") if item.strip()]
    return values or default


@dataclass(frozen=True)
class Settings:
    qdrant_url: str
    qdrant_collection: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    ollama_url: str
    ollama_model: str
    mcp_server_name: str
    tool_policy_path: Path
    default_caller_role: str
    allowed_origins: list[str]
    audit_log_path: Path
    llm_timeout_seconds: int
    llm_max_tokens: int
    max_question_chars: int
    max_context_items: int
    max_evidence_chars: int
    max_answer_chars: int
    max_response_bytes: int


def get_settings() -> Settings:
    root = Path(__file__).resolve().parent
    tool_policy_path = Path(
        os.getenv("RAG_API_TOOL_POLICY_PATH", str(root / "config" / "tool_policies.json"))
    )
    if not tool_policy_path.is_absolute():
        tool_policy_path = root / tool_policy_path

    audit_log_path = Path(
        os.getenv("RAG_API_AUDIT_LOG_PATH", str(root / "logs" / "rag_api_audit.log"))
    )
    if not audit_log_path.is_absolute():
        audit_log_path = root / audit_log_path

    return Settings(
        qdrant_url=os.getenv("QDRANT_URL", "http://qdrant:6333"),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "healthcare_events"),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
        neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
        neo4j_password=os.getenv("NEO4J_PASSWORD", "healthcare123"),
        ollama_url=os.getenv("OLLAMA_URL", "http://ollama:11434"),
        ollama_model=os.getenv("OLLAMA_MODEL", "llama3.1"),
        mcp_server_name=os.getenv("MCP_SERVER_NAME", "HealthcareGraphRAG MCP"),
        tool_policy_path=tool_policy_path,
        default_caller_role=os.getenv("RAG_API_DEFAULT_CALLER_ROLE", "generation"),
        allowed_origins=_split_csv(os.getenv("RAG_API_ALLOW_ORIGINS"), ["*"]),
        audit_log_path=audit_log_path,
        llm_timeout_seconds=int(os.getenv("LLM_TIMEOUT_SECONDS", "120")),
        llm_max_tokens=int(os.getenv("LLM_MAX_TOKENS", "1200")),
        max_question_chars=int(os.getenv("RAG_API_MAX_QUESTION_CHARS", "1000")),
        max_context_items=int(os.getenv("RAG_API_MAX_CONTEXT_ITEMS", "5")),
        max_evidence_chars=int(os.getenv("RAG_API_MAX_EVIDENCE_CHARS", "240")),
        max_answer_chars=int(os.getenv("RAG_API_MAX_ANSWER_CHARS", "2000")),
        max_response_bytes=int(os.getenv("RAG_API_MAX_RESPONSE_BYTES", "50000")),
    )


settings = get_settings()
VECTOR_SIZE = 384

mcp = FastMCP(settings.mcp_server_name)
mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        try:
            yield
        finally:
            neo4j.close()


app = FastAPI(title="Healthcare Hybrid GraphRAG API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "rag_api_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path", "status"],
)
TOOL_EXECUTION_DURATION_SECONDS = Histogram(
    "rag_api_tool_execution_duration_seconds",
    "Tool execution latency in seconds",
    ["tool", "outcome"],
)
TOOL_EXECUTION_TOTAL = Counter(
    "rag_api_tool_execution_total",
    "Tool execution count",
    ["tool", "outcome"],
)


@app.middleware("http")
async def instrument_http_requests(request: Request, call_next):
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        if request.url.path != "/metrics":
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=request.method,
                path=request.url.path,
                status=str(status_code),
            ).observe(time.perf_counter() - started)


qdrant = QdrantClient(url=settings.qdrant_url)
neo4j = GraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password),
)


class AuthorizationError(RuntimeError):
    pass


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)


class PatientContextGetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=128)
    include_claims: bool = True
    include_interactions: bool = True


class VectorEvidenceSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1, le=settings.max_context_items)


class GraphRagAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    response_style: Literal["concise", "clinical", "audit"] = "concise"


class RiskSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=128)
    time_window_hours: int = Field(default=72, ge=1, le=720)


class EvidenceBundleExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    include_raw_payload: bool = False


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_payload(payload: dict[str, Any]) -> str:
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _write_audit_event(event: dict[str, Any]) -> None:
    settings.audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, separators=(",", ":")))
        handle.write("\n")


@lru_cache(maxsize=4)
def load_policy(path: str) -> dict[str, Any]:
    policy_path = Path(path)
    if not policy_path.exists():
        return {"roles": {}}
    with policy_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _authorize(*, tool_name: str, caller_role: str) -> str:
    policy = load_policy(str(settings.tool_policy_path))
    allowed_tools = set(policy.get("roles", {}).get(caller_role, []))
    if tool_name not in allowed_tools:
        raise AuthorizationError(
            f"Role '{caller_role}' is not authorized for tool '{tool_name}'"
        )
    return f"role:{caller_role}"


def _audit(
    *,
    tool_name: str,
    caller_id: str,
    request_payload: dict[str, Any],
    patient_scope: list[str] | str,
    outcome: str,
    latency_ms: int,
    response_size_bytes: int,
    trace_id: str,
    error: str | None = None,
) -> None:
    event = {
        "timestamp": _ts(),
        "trace_id": trace_id,
        "tool_name": tool_name,
        "caller_id": caller_id,
        "input_hash": _hash_payload(request_payload),
        "patient_scope": patient_scope,
        "outcome": outcome,
        "latency_ms": latency_ms,
        "response_size_bytes": response_size_bytes,
    }
    if error:
        event["error"] = error
    _write_audit_event(event)


def stable_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def vector_context(question: str, patient_id: str | None, limit: int) -> list[dict[str, Any]]:
    query_vector = stable_embedding(question)
    query_filter = None
    if patient_id:
        query_filter = {"must": [{"key": "patient_id", "match": {"value": patient_id}}]}

    results = qdrant.search(
        collection_name=settings.qdrant_collection,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
    )
    return [
        {
            "score": result.score,
            "event_id": result.payload.get("event_id"),
            "patient_id": result.payload.get("patient_id"),
            "event_type": result.payload.get("event_type"),
            "text": result.payload.get("text"),
        }
        for result in results
    ]


def graph_context(patient_ids: list[str]) -> list[dict[str, Any]]:
    with neo4j.session() as session:
        records = session.run(
            """
            MATCH (p:Patient)
            WHERE p.id IN $patient_ids

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)
                            RETURN collect(DISTINCT c.name)[..20] AS conditions
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_SYMPTOM]->(s:Symptom)
                            RETURN collect(DISTINCT s.name)[..20] AS symptoms
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)
                            RETURN collect(
                                DISTINCT {name: o.name, value: o.value, unit: o.unit, abnormal: o.abnormal, panel: o.lab_panel, specimen: o.specimen_type}
                            )[..20] AS observations
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
                            RETURN collect(
                                DISTINCT {medication: m.name, drug_class: m.drug_class, dose: mo.dose, route: mo.route, frequency: mo.frequency, order_type: mo.order_type}
                            )[..20] AS medications
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
                            OPTIONAL MATCH (m)-[i:INTERACTS_WITH]->(m2:Medication)
                            RETURN collect(
                                DISTINCT {from: m.name, to: m2.name, risk: i.risk, severity: i.severity}
                            )[..20] AS interactions
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_DEVICE_READING]->(dr:DeviceReading)
                            RETURN collect(
                                DISTINCT {
                                    heart_rate: dr.heart_rate,
                                    spo2: dr.spo2,
                                    bp: toString(dr.systolic_bp) + '/' + toString(dr.diastolic_bp),
                                    temp_c: dr.temperature_c,
                                    rr: dr.respiratory_rate,
                                    alert: dr.alert
                                }
                            )[..20] AS vitals
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_CLAIM]->(cl:Claim)
                            OPTIONAL MATCH (cl)-[:SUBMITTED_TO]->(pay:Payer)
                            OPTIONAL MATCH (cl)-[:FOR_PROCEDURE]->(proc:Procedure)
                            RETURN collect(
                                DISTINCT {payer: coalesce(pay.name, cl.payer), code: proc.code, description: proc.description, status: cl.status, claim_type: cl.claim_type, billed: cl.billed_amount}
                            )[..20] AS claims
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)-[mi:MAY_INDICATE]->(c:Condition)
                            RETURN collect(
                                DISTINCT {observation: o.name, value: o.value, unit: o.unit, indicated_condition: c.name, reason: mi.reason}
                            )[..20] AS lab_signals
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)-[:CODED_AS]->(icd:ICD10Code)
                            RETURN collect(DISTINCT {condition: c.name, icd10: icd.code})[..20] AS icd10_codes
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:REPORTED_ADVERSE_REACTION]->(ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication)
                            RETURN collect(
                                DISTINCT {symptom: ae.symptom_name, medication: m.name, severity: ae.severity, meddra_term: ae.meddra_term}
                            )[..20] AS adverse_events
                        }

                        CALL (p) {
                            OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)<-[ci:CONTRAINDICATED_FOR]-(m:Medication)
                            WHERE EXISTS { MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m) }
                            RETURN collect(
                                DISTINCT {medication: m.name, condition: c.name, reason: ci.reason, severity: ci.severity}
                            )[..10] AS contraindications
                        }

            RETURN p.id AS patient_id,
                                     conditions,
                                     symptoms,
                                     observations,
                                     medications,
                                     interactions,
                                     vitals,
                                     claims,
                                     lab_signals,
                                     icd10_codes,
                                     adverse_events,
                                     contraindications
            """,
            {"patient_ids": patient_ids},
        )
        return [dict(record) for record in records]


def _model_base_name(model_name: str) -> str:
    return model_name.split(":", 1)[0]


def _available_ollama_models() -> list[str]:
    try:
        response = requests.get(f"{settings.ollama_url}/api/tags", timeout=10)
        if response.status_code != 200:
            return []
        models = response.json().get("models", [])
        return [model.get("name") for model in models if model.get("name")]
    except Exception:
        return []


def _resolve_ollama_model() -> tuple[str | None, list[str]]:
    configured = (settings.ollama_model or "").strip()
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


def _compact_vector_context(vector_ctx: list[dict[str, Any]]) -> str:
    if not vector_ctx:
        return "- none"

    lines: list[str] = []
    for item in vector_ctx[: settings.max_context_items]:
        lines.append(
            "- "
            f"patient={item.get('patient_id', 'unknown')} "
            f"event={item.get('event_type', 'unknown')} "
            f"score={float(item.get('score', 0.0)):.3f}"
        )
    return "\n".join(lines)


def _compact_graph_context(graph_ctx: list[dict[str, Any]]) -> str:
    if not graph_ctx:
        return "- none"

    chunks: list[str] = []
    for patient in graph_ctx[: settings.max_context_items]:
        patient_id = patient.get("patient_id", "unknown")
        conditions = ", ".join(patient.get("conditions", [])[:5]) or "none"
        symptoms = ", ".join(patient.get("symptoms", [])[:5]) or "none"

        observations = patient.get("observations", [])[:3]
        observation_summary = "; ".join(
            f"{obs.get('name', 'unknown')}={obs.get('value', 'n/a')}{obs.get('unit', '')}"
            for obs in observations
        ) or "none"

        medications = patient.get("medications", [])[:3]
        medication_summary = "; ".join(
            f"{med.get('medication', 'unknown')} {med.get('dose', '')} {med.get('route', '')}".strip()
            for med in medications
        ) or "none"

        interactions = [i for i in patient.get("interactions", [])[:3] if i.get("to")]
        interaction_summary = "; ".join(
            f"{i.get('from', '?')}+{i.get('to', '?')} ({i.get('risk', '?')}/{i.get('severity', '?')})"
            for i in interactions
        ) or "none"

        lab_signals = patient.get("lab_signals", [])[:5]
        lab_signal_summary = "; ".join(
            f"{s.get('observation', '?')}={s.get('value', '?')} \u2192 {s.get('indicated_condition', '?')}"
            for s in lab_signals
        ) or "none"

        vitals_alerts = [v.get("alert") for v in patient.get("vitals", [])[:5] if v.get("alert")]
        alert_summary = "; ".join(vitals_alerts) or "none"

        adverse_events = patient.get("adverse_events", [])[:3]
        adverse_summary = "; ".join(
            f"{ae.get('symptom', '?')} \u2190 {ae.get('medication', '?')} [{ae.get('severity', '?')}]"
            for ae in adverse_events
        ) or "none"

        contraindications = patient.get("contraindications", [])[:3]
        contra_summary = "; ".join(
            f"{c.get('medication', '?')} \u26a0 {c.get('condition', '?')} ({c.get('reason', '?')})"
            for c in contraindications
        ) or "none"

        chunks.append(
            f"- patient={patient_id}\n"
            f"  conditions={conditions}\n"
            f"  symptoms={symptoms}\n"
            f"  observations={observation_summary}\n"
            f"  lab_signals={lab_signal_summary}\n"
            f"  medications={medication_summary}\n"
            f"  drug_interactions={interaction_summary}\n"
            f"  adverse_events={adverse_summary}\n"
            f"  contraindications={contra_summary}\n"
            f"  device_alerts={alert_summary}"
        )

    return "\n".join(chunks)


def ask_ollama(question: str, vector_ctx: list[dict[str, Any]], graph_ctx: list[dict[str, Any]]) -> str:
    vector_brief = _compact_vector_context(vector_ctx)
    graph_brief = _compact_graph_context(graph_ctx)

    prompt = f"""
You are a clinical decision-support RAG assistant for synthetic demo data only.
Do not provide final medical advice. Summarize likely context and evidence.

Question:
{question}

Vector context from Qdrant:
{vector_brief}

Graph context from Neo4j:
{graph_brief}

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

    try:
        response = requests.post(
            f"{settings.ollama_url}/api/generate",
            json={
                "model": selected_model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_predict": settings.llm_max_tokens,
                    "temperature": 0.2,
                },
            },
            timeout=settings.llm_timeout_seconds,
        )
    except requests.Timeout:
        return (
            "LLM error: Ollama request timed out after "
            f"{settings.llm_timeout_seconds} seconds. "
            "Check model availability, prompt size, or increase LLM_TIMEOUT_SECONDS."
        )
    except requests.RequestException as exc:
        return f"LLM error: unable to reach Ollama at {settings.ollama_url}: {exc}"

    if response.status_code != 200:
        body = response.text
        if "not found" in body.lower():
            available_msg = ", ".join(available_models) if available_models else "none"
            return (
                f"LLM error: requested model '{selected_model}' was not found. "
                f"Configured model: '{settings.ollama_model}'. Available models: {available_msg}. "
                "Pull a model with: docker exec -it healthcare-ollama ollama pull llama3.1"
            )
        return f"LLM error: {body}"
    return str(response.json().get("response") or "")


def run_query(question: str, patient_id: str | None = None, top_k: int | None = None) -> dict[str, Any]:
    context_limit = min(top_k or settings.max_context_items, settings.max_context_items)
    vector_items = vector_context(question, patient_id, context_limit)
    patient_ids = list({item["patient_id"] for item in vector_items if item.get("patient_id")})
    if patient_id:
        patient_ids = list(set(patient_ids + [patient_id]))
    graph_items = graph_context(patient_ids) if patient_ids else []
    answer = ask_ollama(question, vector_items, graph_items)
    return {
        "question": question,
        "patients": patient_ids,
        "vector_context": vector_items,
        "graph_context": graph_items,
        "answer": answer,
    }


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3] + "..."


def _graph_limits(caller_role: str) -> tuple[int, int]:
    if caller_role == "export":
        return settings.max_evidence_chars * 2, settings.max_context_items * 2
    return settings.max_evidence_chars, settings.max_context_items


def _sanitize_graph_value(value: Any, *, text_limit: int, list_limit: int) -> Any:
    if isinstance(value, str):
        return _truncate_text(value, text_limit)
    if isinstance(value, list):
        return [
            _sanitize_graph_value(item, text_limit=text_limit, list_limit=list_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            key: _sanitize_graph_value(item, text_limit=text_limit, list_limit=list_limit)
            for key, item in value.items()
        }
    return value


def _sanitize_vector_context(items: list[dict[str, Any]], *, include_text: bool = False) -> list[dict[str, Any]]:
    sanitized: list[dict[str, Any]] = []
    for item in items[: settings.max_context_items]:
        safe_item = {
            "score": item.get("score"),
            "event_id": item.get("event_id"),
            "patient_id": item.get("patient_id"),
            "event_type": item.get("event_type"),
        }
        text = item.get("text")
        if include_text and text:
            safe_item["text"] = _truncate_text(str(text), settings.max_evidence_chars)
        elif text:
            safe_item["text_redacted"] = True
        sanitized.append(safe_item)
    return sanitized


def _vector_text_mode(caller_role: str, include_raw_payload: bool = False) -> str:
    if caller_role == "export":
        return "bounded"
    if include_raw_payload:
        return "request-denied"
    return "none"


def _sanitize_vector_context_for_role(
    items: list[dict[str, Any]],
    *,
    caller_role: str,
    include_raw_payload: bool = False,
) -> list[dict[str, Any]]:
    text_mode = _vector_text_mode(caller_role, include_raw_payload=include_raw_payload)
    sanitized: list[dict[str, Any]] = []
    for item in items[: settings.max_context_items]:
        safe_item = {
            "score": item.get("score"),
            "event_id": item.get("event_id"),
            "patient_id": item.get("patient_id"),
            "event_type": item.get("event_type"),
        }
        text = item.get("text")
        if text_mode == "bounded" and text:
            safe_item["text"] = _truncate_text(str(text), settings.max_evidence_chars)
        elif text:
            safe_item["text_redacted"] = True
        sanitized.append(safe_item)
    return sanitized


def _sanitize_graph_context_for_role(
    items: list[dict[str, Any]],
    *,
    caller_role: str,
) -> list[dict[str, Any]]:
    text_limit, list_limit = _graph_limits(caller_role)
    return [
        _sanitize_graph_value(item, text_limit=text_limit, list_limit=list_limit)
        for item in items[:list_limit]
    ]


def _apply_response_budget(payload: dict[str, Any]) -> dict[str, Any]:
    payload.setdefault("guardrails", {})
    payload["guardrails"].setdefault("response_truncated", False)

    while len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) > settings.max_response_bytes:
        payload["guardrails"]["response_truncated"] = True
        vector_items = payload.get("vector_context") or []
        if vector_items:
            vector_items.pop()
            continue

        graph_items = payload.get("graph_context") or []
        if graph_items:
            graph_items.pop()
            continue

        answer = payload.get("answer")
        if isinstance(answer, str) and len(answer) > 80:
            payload["answer"] = _truncate_text(answer, max(80, len(answer) - 80))
            continue

        break

    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > settings.max_response_bytes:
        raise RuntimeError("Unable to fit response within configured response budget")
    return payload


def _patient_scope(patient_id: str | None) -> list[str] | str:
    return [patient_id] if patient_id else "cohort"


def _build_query_response(
    result: dict[str, Any],
    trace_id: str,
    *,
    caller_role: str,
) -> dict[str, Any]:
    text_mode = _vector_text_mode(caller_role)
    payload = {
        "question": result["question"],
        "patients": result.get("patients", []),
        "vector_context": _sanitize_vector_context_for_role(
            result.get("vector_context", []),
            caller_role=caller_role,
        ),
        "graph_context": _sanitize_graph_context_for_role(
            result.get("graph_context", []),
            caller_role=caller_role,
        ),
        "answer": _truncate_text(str(result.get("answer") or ""), settings.max_answer_chars),
        "retrieved_at": _ts(),
        "trace_id": trace_id,
        "guardrails": {
            "evidence_text_redacted": text_mode != "bounded",
            "evidence_access_level": text_mode,
            "graph_access_level": "broader" if caller_role == "export" else "standard",
            "max_context_items": settings.max_context_items,
            "max_response_bytes": settings.max_response_bytes,
            "response_truncated": False,
        },
    }
    return _apply_response_budget(payload)


def _execute_with_audit(
    *,
    tool_name: str,
    caller_role: str,
    request_payload: dict[str, Any],
    patient_scope: list[str] | str,
    fn,
) -> dict[str, Any]:
    started_at = time.time()
    trace_id = str(uuid.uuid4())
    caller_id = _authorize(tool_name=tool_name, caller_role=caller_role)
    outcome = "error"
    try:
        response = fn(trace_id)
        outcome = "success"
        response_size = len(json.dumps(response, separators=(",", ":")).encode("utf-8"))
        latency_ms = int((time.time() - started_at) * 1000)
        _audit(
            tool_name=tool_name,
            caller_id=caller_id,
            request_payload=request_payload,
            patient_scope=patient_scope,
            outcome=outcome,
            latency_ms=latency_ms,
            response_size_bytes=response_size,
            trace_id=trace_id,
        )
        return response
    except Exception as exc:
        latency_ms = int((time.time() - started_at) * 1000)
        _audit(
            tool_name=tool_name,
            caller_id=caller_id,
            request_payload=request_payload,
            patient_scope=patient_scope,
            outcome=outcome,
            latency_ms=latency_ms,
            response_size_bytes=0,
            trace_id=trace_id,
            error=str(exc),
        )
        raise
    finally:
        TOOL_EXECUTION_DURATION_SECONDS.labels(tool=tool_name, outcome=outcome).observe(
            max(time.time() - started_at, 0.0)
        )
        TOOL_EXECUTION_TOTAL.labels(tool=tool_name, outcome=outcome).inc()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/mcp/health")
def mcp_health() -> dict[str, Any]:
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
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs", status_code=307)


@app.get("/favicon.ico")
def favicon() -> Response:
    return Response(status_code=204)


@app.post("/query")
def query(
    req: QueryRequest,
    x_caller_role: str | None = Header(default=None, alias="X-Caller-Role"),
) -> dict[str, Any]:
    request_payload = req.model_dump(exclude_none=True)
    caller_role = x_caller_role or settings.default_caller_role
    try:
        return _execute_with_audit(
            tool_name="query",
            caller_role=caller_role,
            request_payload=request_payload,
            patient_scope=_patient_scope(req.patient_id),
            fn=lambda trace_id: _build_query_response(
                run_query(req.question, req.patient_id),
                trace_id,
                caller_role=caller_role,
            ),
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@mcp.tool()
def patient_context_get(
    patient_id: str,
    include_claims: bool = True,
    include_interactions: bool = True,
) -> dict[str, Any]:
    req = PatientContextGetRequest(
        patient_id=patient_id,
        include_claims=include_claims,
        include_interactions=include_interactions,
    )

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query("Return patient graph context for review.", req.patient_id)
        graph_items = _sanitize_graph_context_for_role(
            result.get("graph_context", []),
            caller_role="read_only",
        )
        if not req.include_claims:
            for item in graph_items:
                item.pop("claims", None)
        if not req.include_interactions:
            for item in graph_items:
                item.pop("interactions", None)
        return _apply_response_budget(
            {
                "patient_id": req.patient_id,
                "graph_context": graph_items,
                "retrieved_at": _ts(),
                "trace_id": trace_id,
                "guardrails": {
                    "evidence_text_redacted": True,
                    "evidence_access_level": "none",
                    "graph_access_level": "standard",
                    "max_response_bytes": settings.max_response_bytes,
                    "response_truncated": False,
                },
            }
        )

    return _execute_with_audit(
        tool_name="patient_context_get",
        caller_role="read_only",
        request_payload=req.model_dump(),
        patient_scope=[req.patient_id],
        fn=_handler,
    )


@mcp.tool()
def vector_evidence_search(
    question: str,
    patient_id: str | None = None,
    top_k: int = 5,
) -> dict[str, Any]:
    req = VectorEvidenceSearchRequest(question=question, patient_id=patient_id, top_k=top_k)
    return _execute_with_audit(
        tool_name="vector_evidence_search",
        caller_role="read_only",
        request_payload=req.model_dump(exclude_none=True),
        patient_scope=_patient_scope(req.patient_id),
        fn=lambda trace_id: _apply_response_budget(
            {
                "question": req.question,
                "vector_context": _sanitize_vector_context_for_role(
                    run_query(req.question, req.patient_id, top_k=req.top_k).get("vector_context", []),
                    caller_role="read_only",
                ),
                "retrieved_at": _ts(),
                "trace_id": trace_id,
                "guardrails": {
                    "evidence_text_redacted": True,
                    "evidence_access_level": "none",
                    "graph_access_level": "standard",
                    "max_response_bytes": settings.max_response_bytes,
                    "response_truncated": False,
                },
            }
        ),
    )


@mcp.tool()
def graphrag_answer_generate(
    question: str,
    patient_id: str | None = None,
    response_style: str = "concise",
) -> dict[str, Any]:
    req = GraphRagAnswerRequest(question=question, patient_id=patient_id, response_style=response_style)
    style_prefix = {
        "concise": "Answer concisely. ",
        "clinical": "Use clinically oriented language. ",
        "audit": "Include evidence traceability details. ",
    }
    return _execute_with_audit(
        tool_name="graphrag_answer_generate",
        caller_role="generation",
        request_payload=req.model_dump(exclude_none=True),
        patient_scope=_patient_scope(req.patient_id),
        fn=lambda trace_id: _build_query_response(
            run_query(style_prefix[req.response_style] + req.question, req.patient_id),
            trace_id,
            caller_role="generation",
        ),
    )


@mcp.tool()
def risk_summary_generate(
    patient_id: str,
    time_window_hours: int = 72,
) -> dict[str, Any]:
    req = RiskSummaryRequest(patient_id=patient_id, time_window_hours=time_window_hours)

    def _handler(trace_id: str) -> dict[str, Any]:
        prompt = f"Generate a risk summary for patient {req.patient_id} over the last {req.time_window_hours} hours using available evidence."
        result = run_query(prompt, req.patient_id)
        risk_signals: list[str] = []
        for item in result.get("vector_context", []):
            event_type = item.get("event_type")
            if event_type and event_type not in risk_signals:
                risk_signals.append(event_type)
        return _apply_response_budget(
            {
                "patient_id": req.patient_id,
                "summary": _truncate_text(str(result.get("answer") or ""), settings.max_answer_chars),
                "risk_signals": risk_signals[: settings.max_context_items],
                "retrieved_at": _ts(),
                "trace_id": trace_id,
                "guardrails": {
                    "evidence_text_redacted": True,
                    "evidence_access_level": "none",
                    "graph_access_level": "standard",
                    "max_response_bytes": settings.max_response_bytes,
                    "response_truncated": False,
                },
            }
        )

    return _execute_with_audit(
        tool_name="risk_summary_generate",
        caller_role="generation",
        request_payload=req.model_dump(),
        patient_scope=[req.patient_id],
        fn=_handler,
    )


@mcp.tool()
def evidence_bundle_export(
    question: str,
    patient_id: str | None = None,
    include_raw_payload: bool = False,
) -> dict[str, Any]:
    req = EvidenceBundleExportRequest(question=question, patient_id=patient_id, include_raw_payload=include_raw_payload)

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query(req.question, req.patient_id)
        text_mode = _vector_text_mode("export", include_raw_payload=req.include_raw_payload)
        payload = {
            "question": req.question,
            "patients": result.get("patients", []),
            "vector_context": _sanitize_vector_context_for_role(
                result.get("vector_context", []),
                caller_role="export",
                include_raw_payload=req.include_raw_payload,
            ),
            "graph_context": _sanitize_graph_context_for_role(
                result.get("graph_context", []),
                caller_role="export",
            ),
            "answer": _truncate_text(str(result.get("answer") or ""), settings.max_answer_chars),
            "retrieved_at": _ts(),
            "trace_id": trace_id,
            "guardrails": {
                "evidence_text_redacted": text_mode != "bounded",
                "evidence_access_level": text_mode,
                "graph_access_level": "broader",
                "raw_payload_requested": req.include_raw_payload,
                "raw_payload_returned": False,
                "max_response_bytes": settings.max_response_bytes,
                "response_truncated": False,
            },
        }
        return _apply_response_budget(payload)

    return _execute_with_audit(
        tool_name="evidence_bundle_export",
        caller_role="export",
        request_payload=req.model_dump(exclude_none=True),
        patient_scope=_patient_scope(req.patient_id),
        fn=_handler,
    )


app.mount("/mcp", mcp_http_app)
