from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import get_settings
from .handlers import MCPHandlers


settings = get_settings()
handlers = MCPHandlers(settings)
mcp = FastMCP(settings.server_name)


@mcp.tool()
def patient_context_get(
    patient_id: str,
    include_claims: bool = True,
    include_interactions: bool = True,
    auth_token: str | None = None,
) -> dict:
    request = {
        "patient_id": patient_id,
        "include_claims": include_claims,
        "include_interactions": include_interactions,
    }
    return handlers.patient_context_get(
        request,
        auth_token=auth_token,
        caller_role="read_only",
    )


@mcp.tool()
def vector_evidence_search(
    question: str,
    patient_id: str | None = None,
    top_k: int = 5,
    auth_token: str | None = None,
) -> dict:
    request = {
        "question": question,
        "patient_id": patient_id,
        "top_k": top_k,
    }
    return handlers.vector_evidence_search(
        request,
        auth_token=auth_token,
        caller_role="read_only",
    )


@mcp.tool()
def graphrag_answer_generate(
    question: str,
    patient_id: str | None = None,
    response_style: str = "concise",
    auth_token: str | None = None,
) -> dict:
    request = {
        "question": question,
        "patient_id": patient_id,
        "response_style": response_style,
    }
    return handlers.graphrag_answer_generate(
        request,
        auth_token=auth_token,
        caller_role="generation",
    )


@mcp.tool()
def risk_summary_generate(
    patient_id: str,
    time_window_hours: int = 72,
    auth_token: str | None = None,
) -> dict:
    request = {
        "patient_id": patient_id,
        "time_window_hours": time_window_hours,
    }
    return handlers.risk_summary_generate(
        request,
        auth_token=auth_token,
        caller_role="generation",
    )


@mcp.tool()
def evidence_bundle_export(
    question: str,
    patient_id: str | None = None,
    include_raw_payload: bool = False,
    auth_token: str | None = None,
) -> dict:
    request = {
        "question": question,
        "patient_id": patient_id,
        "include_raw_payload": include_raw_payload,
    }
    return handlers.evidence_bundle_export(
        request,
        auth_token=auth_token,
        caller_role="export",
    )
