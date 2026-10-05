"""HTTP routes: health, discovery, skills planning, and the governed query endpoints."""
from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable, Iterator
from typing import Any

from agent_core.audit import utc_timestamp
from agent_core.governance import ToolGovernance, scope_for
from agent_core.policy import AuthorizationError
from agent_core.streaming import SSE_HEADERS, format_sse
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import RedirectResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from healthcare_agent.agents.registry import AGENT_REGISTRY
from healthcare_agent.api.responses import ResponseShaper
from healthcare_agent.api.schemas import (
    PatientMemoryWriteRequest,
    QueryRequest,
    ResumeRequest,
    SkillsPlanRequest,
)
from healthcare_agent.config.settings import HealthcareAgentSettings
from healthcare_agent.orchestration.query_service import QueryService
from healthcare_agent.tools.skills import SkillsLayerError, build_skill_plan

CALLER_ROLE_HEADER = Header(default=None, alias="X-Caller-Role")
CALLER_ID_HEADER = Header(default=None, alias="X-Caller-Id")


def _dev_entitlements(raw: str) -> dict[str, set[str]]:
    """Parse ``caller=patient,patient`` entries used only by Minikube dev."""
    entitlements: dict[str, set[str]] = {}
    for entry in raw.split(";"):
        caller, separator, patients = entry.partition("=")
        if separator and caller.strip():
            entitlements[caller.strip()] = {item.strip() for item in patients.split(",") if item.strip()}
    return entitlements


def _authorize_dev_patient(
    *, settings: HealthcareAgentSettings, patient_id: str | None, caller_id: str | None
) -> None:
    """Enforce the Minikube identity-to-patient mapping when enabled."""
    if not settings.dev_patient_auth_enabled:
        return
    if not caller_id:
        raise HTTPException(status_code=401, detail="X-Caller-Id is required in the dev environment.")
    if not patient_id:
        raise HTTPException(status_code=403, detail="A patient_id is required for this dev caller.")
    allowed = _dev_entitlements(settings.dev_patient_entitlements).get(caller_id, set())
    if patient_id not in allowed:
        raise HTTPException(status_code=403, detail="Caller is not entitled to this patient.")


def build_router(
    *,
    settings: HealthcareAgentSettings,
    governance: ToolGovernance,
    responses: ResponseShaper,
    queries: QueryService,
    load_skills: Callable[[str], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.get("/metrics")
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.get("/mcp/health")
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

    @router.get("/agents")
    def agents() -> dict[str, Any]:
        """Static LangGraph agent registry, for UI discovery of multi-agent capabilities."""
        return {
            "enabled": True,
            "agents": [
                {
                    "name": card.name,
                    "description": card.description,
                    "capabilities": list(card.capabilities),
                    "accepted_inputs": list(card.accepted_inputs),
                }
                for card in AGENT_REGISTRY.values()
            ],
        }

    @router.post("/skills/plan")
    def skills_plan(req: SkillsPlanRequest, x_caller_role: str | None = CALLER_ROLE_HEADER) -> dict[str, Any]:
        try:
            return governance.execute(
                tool_name="skills_plan_get",
                caller_role=governance.resolve_caller_role(x_caller_role),
                request_payload=req.model_dump(exclude_none=True),
                scope="none",
                fn=lambda trace_id: responses.budget(
                    {
                        **build_skill_plan(
                            load_skills(str(settings.skills_layer_path)),
                            business_goal=req.business_goal,
                            agent=req.agent,
                        ),
                        "retrieved_at": utc_timestamp(),
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

    @router.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse(url="/docs", status_code=307)

    @router.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @router.post("/patient-memory")
    def patient_memory_write(
        req: PatientMemoryWriteRequest,
        x_caller_role: str | None = CALLER_ROLE_HEADER,
        x_caller_id: str | None = CALLER_ID_HEADER,
    ) -> dict[str, Any]:
        _authorize_dev_patient(settings=settings, patient_id=req.patient_id, caller_id=x_caller_id)
        caller_role = governance.resolve_caller_role(x_caller_role)
        try:
            return governance.execute(
                tool_name="patient_memory_write",
                caller_role=caller_role,
                request_payload=req.model_dump(),
                scope=scope_for(req.patient_id),
                fn=lambda trace_id: {
                    "patient_id": req.patient_id,
                    "fact_count": len(
                        queries.write_patient_memory(
                            req.patient_id,
                            req.facts,
                            req.provenance,
                            req.consent,
                        ).facts
                    ),
                    "trace_id": trace_id,
                    "status": "stored",
                },
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/query")
    def query(
        req: QueryRequest,
        x_caller_role: str | None = CALLER_ROLE_HEADER,
        x_caller_id: str | None = CALLER_ID_HEADER,
    ) -> dict[str, Any]:
        _authorize_dev_patient(settings=settings, patient_id=req.patient_id, caller_id=x_caller_id)
        caller_role = governance.resolve_caller_role(x_caller_role)
        try:
            return governance.execute(
                tool_name="query",
                caller_role=caller_role,
                request_payload=req.model_dump(exclude_none=True),
                scope=scope_for(req.patient_id),
                fn=lambda trace_id: responses.query_response(
                    queries.run_query(
                        req.question,
                        req.patient_id,
                        top_k=req.top_k,
                        structured=req.structured,
                        session_id=req.session_id,
                    ),
                    trace_id,
                    caller_role=caller_role,
                ),
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/query/resume")
    def query_resume(
        req: ResumeRequest,
        x_caller_role: str | None = CALLER_ROLE_HEADER,
        x_caller_id: str | None = CALLER_ID_HEADER,
    ) -> dict[str, Any]:
        """Approve or reject a run paused for human review (``status="pending_approval"``).

        Authorization is scoped to the paused run's patient, so a caller cannot
        resume a thread for a patient outside its scope.
        """
        caller_role = governance.resolve_caller_role(x_caller_role)
        request_payload = req.model_dump(exclude_none=True)
        # Role check first so unauthorized callers cannot probe which threads exist.
        try:
            governance.authorize_or_audit_denial(
                tool_name="query",
                caller_role=caller_role,
                request_payload=request_payload,
                scope=scope_for(None),
                started_at=time.time(),
                trace_id=str(uuid.uuid4()),
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        pending = queries.pending_review(req.thread_id)
        if pending is None:
            raise HTTPException(status_code=404, detail="No pending review for this thread_id.")
        _authorize_dev_patient(
            settings=settings, patient_id=pending.get("patient_id"), caller_id=x_caller_id
        )

        def run(trace_id: str) -> dict[str, Any]:
            try:
                result = queries.resume(
                    req.thread_id, req.decision, note=req.note, session_id=req.session_id
                )
            except KeyError as exc:
                raise HTTPException(
                    status_code=404, detail="No pending review for this thread_id."
                ) from exc
            return responses.query_response(result, trace_id, caller_role=caller_role)

        try:
            return governance.execute(
                tool_name="query",
                caller_role=caller_role,
                request_payload=request_payload,
                scope=scope_for(pending.get("patient_id")),
                fn=run,
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @router.post("/query/stream")
    def query_stream(
        req: QueryRequest,
        x_caller_role: str | None = CALLER_ROLE_HEADER,
        x_caller_id: str | None = CALLER_ID_HEADER,
    ) -> StreamingResponse:
        """Stream LangGraph progress as SSE: ``meta``, ``step``*, then ``result`` or ``error``.

        Authorization runs before the stream opens so denied callers get a plain 401.
        Step events carry only allowlisted scalar fields (no evidence); the ``result``
        event is the same role-sanitized, budgeted payload returned by ``/query``.
        """
        tool_name = "query"
        _authorize_dev_patient(settings=settings, patient_id=req.patient_id, caller_id=x_caller_id)
        request_payload = req.model_dump(exclude_none=True)
        caller_role = governance.resolve_caller_role(x_caller_role)
        scope = scope_for(req.patient_id)
        started_at = time.time()
        trace_id = str(uuid.uuid4())
        try:
            caller_id = governance.authorize_or_audit_denial(
                tool_name=tool_name,
                caller_role=caller_role,
                request_payload=request_payload,
                scope=scope,
                started_at=started_at,
                trace_id=trace_id,
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        def events() -> Iterator[str]:
            outcome = "error"
            response_size = 0
            error: str | None = None
            event_id = 0
            try:
                yield format_sse("meta", {"trace_id": trace_id, "orchestrator": "langgraph"}, event_id)
                for kind, data in queries.stream(
                    req.question,
                    req.patient_id,
                    top_k=req.top_k,
                    structured=req.structured,
                    session_id=req.session_id,
                ):
                    event_id += 1
                    if kind == "step":
                        yield format_sse("step", data, event_id)
                        continue
                    body = json.dumps(
                        responses.query_response(data, trace_id, caller_role=caller_role),
                        separators=(",", ":"),
                    )
                    response_size = len(body.encode("utf-8"))
                    outcome = "success"
                    yield format_sse("result", body, event_id)
            except GeneratorExit:
                outcome = "cancelled"
                error = "client disconnected"
                raise
            except Exception as exc:  # surface a structured failure; details stay in the audit log
                error = str(exc)
                yield format_sse(
                    "error",
                    {"detail": f"Query failed ({type(exc).__name__}).", "trace_id": trace_id},
                    event_id + 1,
                )
            finally:
                governance.audit(
                    tool_name=tool_name,
                    caller_id=caller_id,
                    request_payload=request_payload,
                    scope=scope,
                    outcome=outcome,
                    started_at=started_at,
                    response_size_bytes=response_size,
                    trace_id=trace_id,
                    error=error,
                )
                governance.observe(tool_name, outcome, started_at)

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={**SSE_HEADERS, "X-Trace-Id": trace_id},
        )

    return router
