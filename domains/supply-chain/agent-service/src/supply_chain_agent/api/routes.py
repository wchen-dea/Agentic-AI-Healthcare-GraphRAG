"""HTTP routes: health, metrics, skills planning, and the governed query endpoint."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_core.audit import utc_timestamp
from agent_core.governance import ToolGovernance, scope_for
from agent_core.policy import AuthorizationError
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from supply_chain_agent.api.responses import ResponseShaper
from supply_chain_agent.api.schemas import QueryRequest, SkillsPlanRequest
from supply_chain_agent.config.settings import SupplyChainAgentSettings
from supply_chain_agent.orchestration.query_service import QueryService
from supply_chain_agent.tools.skills import SkillsLayerError, build_skill_plan

CALLER_ROLE_HEADER = Header(default=None, alias="X-Caller-Role")
PORTFOLIO_SCOPE = "portfolio"


def build_router(
    *,
    settings: SupplyChainAgentSettings,
    governance: ToolGovernance,
    responses: ResponseShaper,
    queries: QueryService,
    load_skills: Callable[[str], dict[str, Any]],
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "domain": "supply-chain"}

    @router.get("/metrics")
    def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @router.get("/mcp/health")
    def mcp_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mcp": {"enabled": True, "transport": "streamable-http", "endpoint": "/mcp"},
            "skills_layer": {
                "enabled": settings.skills_layer_path.exists(),
                "path": str(settings.skills_layer_path),
            },
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

    @router.post("/query")
    def query(req: QueryRequest, x_caller_role: str | None = CALLER_ROLE_HEADER) -> dict[str, Any]:
        caller_role = governance.resolve_caller_role(x_caller_role)
        try:
            return governance.execute(
                tool_name="query",
                caller_role=caller_role,
                request_payload=req.model_dump(exclude_none=True),
                scope=scope_for(req.entity_id, collective=PORTFOLIO_SCOPE),
                fn=lambda trace_id: responses.query_response(
                    queries.run_query(req.question, req.entity_id), trace_id, caller_role=caller_role
                ),
            )
        except AuthorizationError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return router
