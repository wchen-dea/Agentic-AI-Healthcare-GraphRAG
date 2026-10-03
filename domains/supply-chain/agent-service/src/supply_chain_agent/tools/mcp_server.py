"""Supply-chain MCP tool surface.

Every tool validates its request contract, runs under ``ToolGovernance``
(role policy, audit event, metrics), and answers through ``QueryService`` or
the runtime port so the MCP and HTTP surfaces share one orchestration path.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_core.audit import utc_timestamp
from agent_core.governance import ToolGovernance, scope_for
from agent_core.mcp_server import ToolSpec, register_skills_surface, register_tools
from mcp.server.fastmcp import FastMCP

from supply_chain_agent.api.responses import ResponseShaper
from supply_chain_agent.api.schemas import (
    EntityRequest,
    EvidenceBundleExportRequest,
    GraphRagAnswerRequest,
    SkillsPlanRequest,
    VectorEvidenceSearchRequest,
)
from supply_chain_agent.config.settings import SupplyChainAgentSettings
from supply_chain_agent.orchestration.query_service import QueryService
from supply_chain_agent.orchestration.runtime import get_runtime
from supply_chain_agent.tools.skills import build_skill_plan

PORTFOLIO_SCOPE = "portfolio"

# Descriptions fall back to each tool method's docstring.
TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("supplier_context_get", "Supplier context", "read_only"),
    ToolSpec("vector_evidence_search", "Vector evidence search", "read_only"),
    ToolSpec("graphrag_answer_generate", "GraphRAG answer", "generation"),
    ToolSpec("risk_summary_generate", "Supplier risk summary", "generation"),
    ToolSpec("disruption_impact_assess", "Disruption impact", "generation"),
    ToolSpec("inventory_reorder_check", "Inventory reorder check", "generation"),
    ToolSpec("evidence_bundle_export", "Evidence bundle export", "export"),
    ToolSpec("skills_plan_get", "Skills plan", "read_only"),
)
TOOL_NAMES = tuple(spec.name for spec in TOOL_SPECS)

_STYLE_PREFIX = {
    "concise": "Answer concisely. ",
    "operational": "Use operations-planning language. ",
    "audit": "Include evidence traceability details. ",
}


class SupplyChainMcpTools:
    def __init__(
        self,
        *,
        settings: SupplyChainAgentSettings,
        governance: ToolGovernance,
        responses: ResponseShaper,
        queries: QueryService,
        load_skills: Callable[[str], dict[str, Any]],
    ) -> None:
        self._settings = settings
        self._governance = governance
        self._responses = responses
        self._queries = queries
        self._load_skills = load_skills

    def register(self, mcp: FastMCP) -> None:
        register_tools(mcp, self, TOOL_SPECS)
        register_skills_surface(
            mcp,
            lambda: self._load_skills(str(self._settings.skills_layer_path)),
            prompt_name="supply_risk_review",
            prompt_title="Supply risk review plan",
            subject_label="Entity",
        )

    def _generate(self, tool_name: str, prompt: str, entity_id: str | None, payload: dict[str, Any]) -> dict[str, Any]:
        return self._governance.execute(
            tool_name=tool_name,
            caller_role="generation",
            request_payload=payload,
            scope=scope_for(entity_id, collective=PORTFOLIO_SCOPE),
            fn=lambda trace_id: self._responses.query_response(
                self._queries.run_query(prompt, entity_id), trace_id, caller_role="generation"
            ),
        )

    def supplier_context_get(self, entity_id: str) -> dict[str, Any]:
        """Return bounded graph context (parts, risks, disruptions, quality, inventory) for one entity."""
        req = EntityRequest(entity_id=entity_id)
        return self._governance.execute(
            tool_name="supplier_context_get",
            caller_role="read_only",
            request_payload=req.model_dump(),
            scope=[req.entity_id],
            fn=lambda trace_id: self._responses.budget(
                {
                    "entity_id": req.entity_id,
                    "graph_context": self._responses.sanitize_graph(
                        get_runtime().graph_search([req.entity_id]), caller_role="read_only"
                    ),
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": self._responses.guardrails("read_only"),
                }
            ),
        )

    def vector_evidence_search(self, question: str, entity_id: str = "", top_k: int = 5) -> dict[str, Any]:
        """Search supply-chain event evidence; text is redacted for this role."""
        req = VectorEvidenceSearchRequest(question=question, entity_id=(entity_id or None), top_k=top_k)
        limit = self._queries.context_limit(req.top_k)
        return self._governance.execute(
            tool_name="vector_evidence_search",
            caller_role="read_only",
            request_payload=req.model_dump(exclude_none=True),
            scope=scope_for(req.entity_id, collective=PORTFOLIO_SCOPE),
            fn=lambda trace_id: self._responses.budget(
                {
                    "question": req.question,
                    "vector_context": self._responses.sanitize_vector(
                        get_runtime().vector_search(req.question, req.entity_id, limit), caller_role="read_only"
                    ),
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": self._responses.guardrails("read_only"),
                }
            ),
        )

    def graphrag_answer_generate(
        self, question: str, entity_id: str = "", response_style: str = "concise"
    ) -> dict[str, Any]:
        """Generate a grounded GraphRAG answer through the LangGraph orchestration."""
        req = GraphRagAnswerRequest(question=question, entity_id=(entity_id or None), response_style=response_style)
        return self._generate(
            "graphrag_answer_generate",
            _STYLE_PREFIX[req.response_style] + req.question,
            req.entity_id,
            req.model_dump(exclude_none=True),
        )

    def risk_summary_generate(self, entity_id: str) -> dict[str, Any]:
        """Summarize supplier risk signals for one entity."""
        req = EntityRequest(entity_id=entity_id)
        return self._generate(
            "risk_summary_generate",
            f"Summarize supplier risk signals and exposure for {req.entity_id}.",
            req.entity_id,
            req.model_dump(),
        )

    def disruption_impact_assess(self, entity_id: str) -> dict[str, Any]:
        """Assess active disruption impact and mitigation status for one entity."""
        req = EntityRequest(entity_id=entity_id)
        return self._generate(
            "disruption_impact_assess",
            f"Assess the impact of active disruptions affecting {req.entity_id} and their mitigation status.",
            req.entity_id,
            req.model_dump(),
        )

    def inventory_reorder_check(self, entity_id: str) -> dict[str, Any]:
        """Check inventory positions below reorder point for one entity."""
        req = EntityRequest(entity_id=entity_id)
        return self._generate(
            "inventory_reorder_check",
            f"Identify inventory positions below reorder point and reorder priorities for {req.entity_id}.",
            req.entity_id,
            req.model_dump(),
        )

    def evidence_bundle_export(
        self, question: str, entity_id: str = "", include_raw_payload: bool = False
    ) -> dict[str, Any]:
        """Export an audit evidence bundle with bounded evidence text."""
        req = EvidenceBundleExportRequest(
            question=question, entity_id=(entity_id or None), include_raw_payload=include_raw_payload
        )
        return self._governance.execute(
            tool_name="evidence_bundle_export",
            caller_role="export",
            request_payload=req.model_dump(exclude_none=True),
            scope=scope_for(req.entity_id, collective=PORTFOLIO_SCOPE),
            fn=lambda trace_id: self._responses.query_response(
                self._queries.run_query(req.question, req.entity_id),
                trace_id,
                caller_role="export",
                include_raw_payload=req.include_raw_payload,
            ),
        )

    def skills_plan_get(self, business_goal: str, agent: str = "") -> dict[str, Any]:
        """Resolve a business goal into the agent, skills, and MCP tools to use."""
        req = SkillsPlanRequest(business_goal=business_goal, agent=(agent or None))
        return self._governance.execute(
            tool_name="skills_plan_get",
            caller_role="read_only",
            request_payload=req.model_dump(exclude_none=True),
            scope="none",
            fn=lambda trace_id: self._responses.budget(
                {
                    **build_skill_plan(
                        self._load_skills(str(self._settings.skills_layer_path)),
                        business_goal=req.business_goal,
                        agent=req.agent,
                    ),
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                }
            ),
        )
