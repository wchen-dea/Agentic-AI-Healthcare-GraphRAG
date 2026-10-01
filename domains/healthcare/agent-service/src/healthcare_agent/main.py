"""Composition root for the healthcare agent service.

Wires settings, data stores, the LLM gateway, the LangGraph runtime ports,
governance, the HTTP API, and the MCP tool surface. ASGI entrypoint:
``uvicorn healthcare_agent.main:app``.

Adapters below are module globals and the runtime binds them through lambdas,
so tests can patch ``main.vector_context`` / ``main.ask_ollama`` after import.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from functools import lru_cache
from typing import Any

from agent_core.governance import ToolGovernance
from agent_core.metrics import ServiceMetrics
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from mcp.server.fastmcp import FastMCP
from neo4j import GraphDatabase
from qdrant_client import QdrantClient

from healthcare_agent.api.responses import ResponseShaper
from healthcare_agent.api.routes import build_router
from healthcare_agent.api.schemas import RequestLimits, configure_request_limits
from healthcare_agent.config.settings import load_settings
from healthcare_agent.generation.factory import build_llm_provider, llm_model_info
from healthcare_agent.generation.structured_output import build_structured_prompt, parse_structured_response
from healthcare_agent.generation.synthesis import compact_graph_context, compact_vector_context, synthesize_answer
from healthcare_agent.orchestration.orchestrator import LangGraphOrchestrator
from healthcare_agent.orchestration.query_service import QueryService
from healthcare_agent.orchestration.runtime import AgentRuntime, configure_runtime
from healthcare_agent.retrieval.search import graph_search, vector_search
from healthcare_agent.tools.mcp_server import HealthcareMcpTools
from healthcare_agent.tools.skills import load_skills_layer

settings = load_settings()
configure_request_limits(
    RequestLimits(max_question_chars=settings.max_question_chars, max_context_items=settings.max_context_items)
)
metrics = ServiceMetrics.register()

# ── Data stores and LLM gateway ─────────────────────────────────────────────

qdrant = QdrantClient(url=settings.qdrant_url)
neo4j = GraphDatabase.driver(
    settings.neo4j_uri,
    auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
)
llm_provider = build_llm_provider(settings)


def vector_context(question: str, patient_id: str | None, limit: int) -> list[dict[str, Any]]:
    return vector_search(qdrant, settings.qdrant_collection, question, patient_id, limit)


def graph_context(patient_ids: list[str]) -> list[dict[str, Any]]:
    return graph_search(neo4j, patient_ids)


def _ask_ollama_impl(question: str, vector_ctx: list[dict[str, Any]], graph_ctx: list[dict[str, Any]]) -> str:
    return synthesize_answer(
        question,
        vector_ctx,
        graph_ctx,
        llm_provider,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
        max_items=settings.max_context_items,
    )


if settings.mlflow_tracking_uri:
    from healthcare_agent.observability.tracing import trace_llm_call

    ask_ollama = trace_llm_call(_ask_ollama_impl, get_model_info=lambda: llm_model_info(llm_provider, settings))
else:
    ask_ollama = _ask_ollama_impl


def _synthesize_structured_impl(
    question: str, vector_ctx: list[dict[str, Any]], graph_ctx: list[dict[str, Any]]
) -> dict[str, Any]:
    prompt = build_structured_prompt(
        question,
        compact_vector_context(vector_ctx, max_items=settings.max_context_items),
        compact_graph_context(graph_ctx, max_items=settings.max_context_items),
    )
    raw = llm_provider.generate(
        prompt=prompt,
        timeout_seconds=settings.llm_timeout_seconds,
        max_tokens=settings.llm_max_tokens,
        temperature=0.1,
        question=question,
    )
    return parse_structured_response(raw).model_dump()


# Bind the LangGraph tool-gateway port to in-process adapters. A future
# MCP-client adapter replaces this binding without touching agent code
# (docs/adrs/0010-layered-agentic-architecture.md).
configure_runtime(
    AgentRuntime(
        vector_search=lambda query_text, patient_id, limit: vector_context(query_text, patient_id, limit),
        graph_search=lambda patient_ids: graph_context(patient_ids),
        synthesize=lambda question, vector_ctx, graph_ctx: ask_ollama(question, vector_ctx, graph_ctx),
        synthesize_structured=lambda question, vector_ctx, graph_ctx: _synthesize_structured_impl(
            question, vector_ctx, graph_ctx
        ),
    )
)

# ── Application services ────────────────────────────────────────────────────


@lru_cache(maxsize=2)
def load_skills(path: str) -> dict[str, Any]:
    return load_skills_layer(path)


# Healthcare audit events keep the `patient_scope` key (audit schema contract).
governance = ToolGovernance(settings, metrics, audit_scope_key="patient_scope")
responses = ResponseShaper(settings)
orchestrator = LangGraphOrchestrator.build()
queries = QueryService(
    max_context_items=settings.max_context_items,
    orchestrator=orchestrator,
)
mcp_tools = HealthcareMcpTools(
    settings=settings, governance=governance, responses=responses, queries=queries, load_skills=load_skills
)

# ── Transports: MCP (streamable HTTP at /mcp) and the FastAPI app ───────────

mcp = FastMCP(settings.mcp_server_name)
mcp_tools.register(mcp)
mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():
        try:
            yield
        finally:
            neo4j.close()


app = FastAPI(title="Healthcare Agent Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browser MCP clients must read the session id returned by `initialize`.
    expose_headers=["mcp-session-id"],
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
            metrics.observe_http(request.method, request.url.path, status_code, time.perf_counter() - started)


app.include_router(
    build_router(
        settings=settings, governance=governance, responses=responses, queries=queries, load_skills=load_skills
    )
)
app.router.routes.extend(mcp_http_app.routes)
