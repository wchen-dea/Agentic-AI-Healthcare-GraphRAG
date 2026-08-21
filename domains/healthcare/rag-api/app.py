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

from domain import (
    apply_response_budget,
    classify_request_type,
    rank_graph_context,
    rank_vector_context,
    sanitize_graph_context_for_role,
    sanitize_vector_context_for_role,
    select_retrieval_plan,
    truncate_text,
    vector_text_mode,
)
from domain.react_controller import ReactLoopSettings, run_react_query_loop
from domain.retrieval import VECTOR_SIZE, graph_search, stable_embedding, vector_search
from domain.synthesis import synthesize_answer
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from llm_provider import LLMProviderError, create_provider
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase
from pydantic import BaseModel, ConfigDict, Field
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from qdrant_client import QdrantClient
from skills_layer import SkillsLayerError, build_skill_plan, load_skills_layer


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
    llm_provider: str
    mcp_server_name: str
    tool_policy_path: Path
    skills_layer_path: Path
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
    react_enabled: bool
    react_max_iters: int
    react_min_confidence: float
    react_max_no_progress_steps: int


def get_settings() -> Settings:
    root = Path(__file__).resolve().parent
    tool_policy_path = Path(
        os.getenv("RAG_API_TOOL_POLICY_PATH", str(root / "config" / "tool_policies.json"))
    )
    if not tool_policy_path.is_absolute():
        tool_policy_path = root / tool_policy_path

    skills_layer_path = Path(
        os.getenv("RAG_API_SKILLS_LAYER_PATH", str(root / "config" / "skills_layer.json"))
    )
    if not skills_layer_path.is_absolute():
        skills_layer_path = root / skills_layer_path

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
        llm_provider=os.getenv("LLM_PROVIDER", "ollama"),
        mcp_server_name=os.getenv("MCP_SERVER_NAME", "HealthcareGraphRAG MCP"),
        tool_policy_path=tool_policy_path,
        skills_layer_path=skills_layer_path,
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
        react_enabled=_to_bool(os.getenv("RAG_API_REACT_ENABLED"), default=False),
        react_max_iters=max(1, min(int(os.getenv("RAG_API_REACT_MAX_ITERS", "3")), 6)),
        react_min_confidence=max(
            0.0,
            min(float(os.getenv("RAG_API_REACT_MIN_CONFIDENCE", "0.75")), 1.0),
        ),
        react_max_no_progress_steps=max(
            0,
            int(os.getenv("RAG_API_REACT_MAX_NO_PROGRESS_STEPS", "1")),
        ),
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
llm_provider = create_provider(
    settings.llm_provider,
    base_url=settings.ollama_url,
    configured_model=settings.ollama_model,
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


class TimelineExplainRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=128)
    time_window_hours: int = Field(default=168, ge=1, le=720)


class MedicationRiskAssessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=128)


class CodingGapDetectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str = Field(min_length=1, max_length=128)
    question: str = Field(
        default="Review coding and claims consistency gaps for this patient.",
        min_length=3,
        max_length=settings.max_question_chars,
    )


class CohortRiskSummaryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=settings.max_question_chars)
    top_k: int = Field(default=5, ge=1, le=max(settings.max_context_items, 8))


class SkillsPlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_goal: str = Field(min_length=3, max_length=128)
    agent: str | None = Field(default=None, min_length=1, max_length=128)


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


@lru_cache(maxsize=2)
def load_skills(path: str) -> dict[str, Any]:
    return load_skills_layer(path)


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


_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


def vector_context(question: str, patient_id: str | None, limit: int) -> list[dict[str, Any]]:
    return vector_search(qdrant, settings.qdrant_collection, question, patient_id, limit)


def graph_context(patient_ids: list[str]) -> list[dict[str, Any]]:
    return graph_search(neo4j, patient_ids)


def ask_ollama(question: str, vector_ctx: list[dict[str, Any]], graph_ctx: list[dict[str, Any]]) -> str:
    return synthesize_answer(
        question, vector_ctx, graph_ctx, llm_provider,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
        max_items=settings.max_context_items,
    )


def run_query(question: str, patient_id: str | None = None, top_k: int | None = None) -> dict[str, Any]:
    context_limit = min(top_k or settings.max_context_items, max(settings.max_context_items, 8))

    # LangGraph multi-agent path (takes priority when enabled)
    if _to_bool(os.getenv("RAG_API_LANGGRAPH_ENABLED"), default=False):
        from langgraph_agents import run_langgraph_query
        return run_langgraph_query(question=question, patient_id=patient_id)

    # MLflow tracing for single-pass / ReAct when MLFLOW_TRACKING_URI is set
    if os.getenv("MLFLOW_TRACKING_URI"):
        from langgraph_agents.mlflow_tracing import trace_query
        mode = "react" if settings.react_enabled else "single_pass"
        return trace_query(question, patient_id, mode, _run_query_core, top_k=top_k)

    return _run_query_core(question, patient_id, top_k)


def _run_query_core(question: str, patient_id: str | None = None, top_k: int | None = None) -> dict[str, Any]:
    context_limit = min(top_k or settings.max_context_items, max(settings.max_context_items, 8))

    if settings.react_enabled:
        loop_settings = ReactLoopSettings(
            max_iterations=settings.react_max_iters,
            min_confidence=settings.react_min_confidence,
            max_no_progress_steps=settings.react_max_no_progress_steps,
        )
        return run_react_query_loop(
            question=question,
            patient_id=patient_id,
            context_limit=context_limit,
            settings=loop_settings,
            classify_request_type_fn=classify_request_type,
            select_retrieval_plan_fn=select_retrieval_plan,
            vector_context_fn=vector_context,
            rank_vector_context_fn=rank_vector_context,
            graph_context_fn=graph_context,
            rank_graph_context_fn=rank_graph_context,
            synthesize_answer_fn=ask_ollama,
        )

    return _run_query_single_pass(question=question, patient_id=patient_id, context_limit=context_limit)


def _run_query_single_pass(
    *,
    question: str,
    patient_id: str | None,
    context_limit: int,
) -> dict[str, Any]:
    request_type = classify_request_type(question, patient_id)
    plan = select_retrieval_plan(request_type, question, patient_id, context_limit)

    vector_items_raw = vector_context(plan.query_text, patient_id, plan.top_k)
    vector_items = rank_vector_context(vector_items_raw, request_type)
    patient_ids = list({item["patient_id"] for item in vector_items if item.get("patient_id")})
    if patient_id:
        patient_ids = list(set(patient_ids + [patient_id]))
    graph_items_raw = graph_context(patient_ids) if patient_ids else []
    graph_items = rank_graph_context(graph_items_raw, request_type)
    answer = ask_ollama(question, vector_items, graph_items)
    return {
        "question": question,
        "request_type": request_type,
        "retrieval_plan": {
            "name": plan.name,
            "top_k": plan.top_k,
            "reason": plan.reason,
        },
        "patients": patient_ids,
        "vector_context": vector_items,
        "graph_context": graph_items,
        "answer": answer,
    }


def _patient_scope(patient_id: str | None) -> list[str] | str:
    return [patient_id] if patient_id else "cohort"


def _sanitize_vector(items, *, caller_role, include_raw_payload=False):
    return sanitize_vector_context_for_role(
        items, caller_role=caller_role, include_raw_payload=include_raw_payload,
        max_context_items=settings.max_context_items, max_evidence_chars=settings.max_evidence_chars,
    )


def _sanitize_graph(items, *, caller_role):
    return sanitize_graph_context_for_role(
        items, caller_role=caller_role,
        max_evidence_chars=settings.max_evidence_chars, max_context_items=settings.max_context_items,
    )


def _build_query_response(
    result: dict[str, Any],
    trace_id: str,
    *,
    caller_role: str,
) -> dict[str, Any]:
    text_mode = vector_text_mode(caller_role)
    payload = {
        "question": result["question"],
        "request_type": result.get("request_type"),
        "retrieval_plan": result.get("retrieval_plan"),
        "patients": result.get("patients", []),
        "vector_context": _sanitize_vector(
            result.get("vector_context", []),
            caller_role=caller_role,
        ),
        "graph_context": _sanitize_graph(
            result.get("graph_context", []),
            caller_role=caller_role,
        ),
        "answer": truncate_text(str(result.get("answer") or ""), settings.max_answer_chars),
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
    if result.get("react"):
        payload["react"] = result["react"]
    return apply_response_budget(payload, max_response_bytes=settings.max_response_bytes)


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
        "skills_layer": {
            "enabled": settings.skills_layer_path.exists(),
            "path": str(settings.skills_layer_path),
        },
    }


@app.post("/skills/plan")
def skills_plan(
    req: SkillsPlanRequest,
    x_caller_role: str | None = Header(default=None, alias="X-Caller-Role"),
) -> dict[str, Any]:
    request_payload = req.model_dump(exclude_none=True)
    caller_role = x_caller_role or settings.default_caller_role
    try:
        return _execute_with_audit(
            tool_name="skills_plan_get",
            caller_role=caller_role,
            request_payload=request_payload,
            patient_scope="none",
            fn=lambda trace_id: apply_response_budget(
                {
                    **build_skill_plan(
                        load_skills(str(settings.skills_layer_path)),
                        business_goal=req.business_goal,
                        agent=req.agent,
                    ),
                    "retrieved_at": _ts(),
                    "trace_id": trace_id,
                }
            ),
        )
    except AuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except SkillsLayerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


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
        graph_items = _sanitize_graph(
            result.get("graph_context", []),
            caller_role="read_only",
        )
        if not req.include_claims:
            for item in graph_items:
                item.pop("claims", None)
        if not req.include_interactions:
            for item in graph_items:
                item.pop("interactions", None)
        return apply_response_budget(
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
    patient_id: str = "",
    top_k: int = 5,
) -> dict[str, Any]:
    req = VectorEvidenceSearchRequest(question=question, patient_id=(patient_id or None), top_k=top_k)
    return _execute_with_audit(
        tool_name="vector_evidence_search",
        caller_role="read_only",
        request_payload=req.model_dump(exclude_none=True),
        patient_scope=_patient_scope(req.patient_id),
        fn=lambda trace_id: apply_response_budget(
            {
                "question": req.question,
                "vector_context": _sanitize_vector(
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
    patient_id: str = "",
    response_style: str = "concise",
) -> dict[str, Any]:
    req = GraphRagAnswerRequest(question=question, patient_id=(patient_id or None), response_style=response_style)
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
        return apply_response_budget(
            {
                "patient_id": req.patient_id,
                "summary": truncate_text(str(result.get("answer") or ""), settings.max_answer_chars),
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
    patient_id: str = "",
    include_raw_payload: bool = False,
) -> dict[str, Any]:
    req = EvidenceBundleExportRequest(question=question, patient_id=(patient_id or None), include_raw_payload=include_raw_payload)

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query(req.question, req.patient_id)
        text_mode = vector_text_mode("export", include_raw_payload=req.include_raw_payload)
        payload = {
            "question": req.question,
            "patients": result.get("patients", []),
            "vector_context": _sanitize_vector(
                result.get("vector_context", []),
                caller_role="export",
                include_raw_payload=req.include_raw_payload,
            ),
            "graph_context": _sanitize_graph(
                result.get("graph_context", []),
                caller_role="export",
            ),
            "answer": truncate_text(str(result.get("answer") or ""), settings.max_answer_chars),
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
        return apply_response_budget(payload, max_response_bytes=settings.max_response_bytes)

    return _execute_with_audit(
        tool_name="evidence_bundle_export",
        caller_role="export",
        request_payload=req.model_dump(exclude_none=True),
        patient_scope=_patient_scope(req.patient_id),
        fn=_handler,
    )


@mcp.tool()
def timeline_explain(
    patient_id: str,
    time_window_hours: int = 168,
) -> dict[str, Any]:
    req = TimelineExplainRequest(patient_id=patient_id, time_window_hours=time_window_hours)

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query(
            f"Explain timeline progression for patient {req.patient_id} across the last {req.time_window_hours} hours.",
            req.patient_id,
        )
        graph_items = _sanitize_graph(
            result.get("graph_context", []),
            caller_role="generation",
        )
        return apply_response_budget(
            {
                "patient_id": req.patient_id,
                "time_window_hours": req.time_window_hours,
                "timeline_summary": truncate_text(
                    str(result.get("answer") or ""), settings.max_answer_chars
                ),
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
        tool_name="timeline_explain",
        caller_role="generation",
        request_payload=req.model_dump(),
        patient_scope=[req.patient_id],
        fn=_handler,
    )


@mcp.tool()
def medication_risk_assess(patient_id: str) -> dict[str, Any]:
    req = MedicationRiskAssessRequest(patient_id=patient_id)

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query(
            f"Assess medication risk, contraindications, interactions, and adverse events for patient {req.patient_id}.",
            req.patient_id,
        )
        graph_items = result.get("graph_context", [])
        first_patient = graph_items[0] if graph_items else {}
        return apply_response_budget(
            {
                "patient_id": req.patient_id,
                "risk_assessment": truncate_text(
                    str(result.get("answer") or ""), settings.max_answer_chars
                ),
                "contraindications": first_patient.get("contraindications", [])[: settings.max_context_items],
                "adverse_events": first_patient.get("adverse_events", [])[: settings.max_context_items],
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
        tool_name="medication_risk_assess",
        caller_role="generation",
        request_payload=req.model_dump(),
        patient_scope=[req.patient_id],
        fn=_handler,
    )


@mcp.tool()
def coding_gap_detect(
    patient_id: str,
    question: str = "Review coding and claims consistency gaps for this patient.",
) -> dict[str, Any]:
    req = CodingGapDetectRequest(patient_id=patient_id, question=question)

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query(req.question, req.patient_id)
        graph_items = result.get("graph_context", [])
        first_patient = graph_items[0] if graph_items else {}
        return apply_response_budget(
            {
                "patient_id": req.patient_id,
                "coding_gap_summary": truncate_text(
                    str(result.get("answer") or ""), settings.max_answer_chars
                ),
                "claims": first_patient.get("claims", [])[: settings.max_context_items],
                "icd10_codes": first_patient.get("icd10_codes", [])[: settings.max_context_items],
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
        tool_name="coding_gap_detect",
        caller_role="generation",
        request_payload=req.model_dump(),
        patient_scope=[req.patient_id],
        fn=_handler,
    )


@mcp.tool()
def cohort_risk_summary(
    question: str,
    top_k: int = 5,
) -> dict[str, Any]:
    req = CohortRiskSummaryRequest(question=question, top_k=top_k)

    def _handler(trace_id: str) -> dict[str, Any]:
        result = run_query(req.question, patient_id=None, top_k=req.top_k)
        return apply_response_budget(
            {
                "question": req.question,
                "cohort_summary": truncate_text(
                    str(result.get("answer") or ""), settings.max_answer_chars
                ),
                "patients": result.get("patients", []),
                "vector_context": _sanitize_vector(
                    result.get("vector_context", []),
                    caller_role="generation",
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
        )

    return _execute_with_audit(
        tool_name="cohort_risk_summary",
        caller_role="generation",
        request_payload=req.model_dump(),
        patient_scope="cohort",
        fn=_handler,
    )


@mcp.tool()
def skills_plan_get(
    business_goal: str,
    agent: str = "",
) -> dict[str, Any]:
    req = SkillsPlanRequest(business_goal=business_goal, agent=(agent or None))

    def _handler(trace_id: str) -> dict[str, Any]:
        return apply_response_budget(
            {
                **build_skill_plan(
                    load_skills(str(settings.skills_layer_path)),
                    business_goal=req.business_goal,
                    agent=req.agent,
                ),
                "retrieved_at": _ts(),
                "trace_id": trace_id,
            }
        )

    return _execute_with_audit(
        tool_name="skills_plan_get",
        caller_role="read_only",
        request_payload=req.model_dump(exclude_none=True),
        patient_scope="none",
        fn=_handler,
    )


app.mount("/mcp", mcp_http_app)
