"""Healthcare MCP tool surface.

Every tool validates its request contract, runs under ``ToolGovernance``
(role policy, audit event, metrics), and answers through ``QueryService`` so
the MCP and HTTP surfaces share one orchestration path.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_core.audit import utc_timestamp
from agent_core.governance import ToolGovernance, scope_for
from agent_core.mcp_server import ToolSpec, register_skills_surface, register_tools
from mcp.server.fastmcp import FastMCP

from healthcare_agent.api.responses import ResponseShaper
from healthcare_agent.api.schemas import (
    CodingGapDetectRequest,
    CohortRiskSummaryRequest,
    EvidenceBundleExportRequest,
    GraphRagAnswerRequest,
    MedicationRiskAssessRequest,
    PatientContextGetRequest,
    PatientMemoryWriteRequest,
    RiskSummaryRequest,
    SkillsPlanRequest,
    TimelineExplainRequest,
    VectorEvidenceSearchRequest,
)
from healthcare_agent.config.settings import HealthcareAgentSettings
from healthcare_agent.orchestration.query_service import QueryService
from healthcare_agent.safety.response_policy import apply_response_budget, truncate_text, vector_text_mode
from healthcare_agent.tools.skills import build_skill_plan

TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        "patient_context_get",
        "Patient context",
        "read_only",
        "Return a patient's graph context: conditions, medications, claims and drug interactions.",
    ),
    ToolSpec(
        "vector_evidence_search",
        "Vector evidence search",
        "read_only",
        "Semantic search over clinical notes and evidence chunks, optionally scoped to one patient.",
    ),
    ToolSpec(
        "graphrag_answer_generate",
        "GraphRAG answer",
        "generation",
        "Answer a clinical question with graph and vector evidence, returning citations.",
    ),
    ToolSpec(
        "risk_summary_generate",
        "Patient risk summary",
        "generation",
        "Generate an evidence-grounded clinical risk summary for one patient.",
    ),
    ToolSpec(
        "evidence_bundle_export",
        "Evidence bundle export",
        "export",
        "Export the audit-ready evidence bundle (graph facts and vector hits) for a patient question.",
    ),
    ToolSpec(
        "timeline_explain",
        "Clinical timeline",
        "generation",
        "Explain a patient's clinical timeline of encounters, diagnoses and medications.",
    ),
    ToolSpec(
        "medication_risk_assess",
        "Medication risk",
        "generation",
        "Assess medication risks such as interactions and contraindications for a patient.",
    ),
    ToolSpec(
        "coding_gap_detect",
        "Coding gap detection",
        "generation",
        "Detect documentation or coding gaps between clinical evidence and recorded codes.",
    ),
    ToolSpec(
        "cohort_risk_summary",
        "Cohort risk summary",
        "generation",
        "Summarize risk patterns across a patient cohort.",
    ),
    ToolSpec(
        "skills_plan_get",
        "Skills plan",
        "read_only",
        "Return the skill plan (skills, context requirements, tools) for a business goal.",
    ),
    ToolSpec(
        "patient_memory_write",
        "Patient memory write",
        "memory_write",
        "Store a consented, provenance-bearing minimized patient memory fact set.",
    ),
)
TOOL_NAMES = tuple(spec.name for spec in TOOL_SPECS)


class HealthcareMcpTools:
    def __init__(
        self,
        *,
        settings: HealthcareAgentSettings,
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
            prompt_name="clinical_review",
            prompt_title="Clinical review plan",
            subject_label="Patient",
        )

    def patient_memory_write(
        self,
        patient_id: str,
        facts: list[dict[str, object]],
        provenance: dict[str, object] | str,
        consent: bool,
    ) -> dict[str, Any]:
        req = PatientMemoryWriteRequest(
            patient_id=patient_id,
            facts=facts,
            provenance=provenance,
            consent=consent,
        )
        return self._governance.execute(
            tool_name="patient_memory_write",
            caller_role="memory_write",
            request_payload=req.model_dump(),
            scope=[req.patient_id],
            fn=lambda trace_id: {
                "patient_id": req.patient_id,
                "fact_count": len(
                    self._queries.write_patient_memory(
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

    def patient_context_get(
        self,
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
            result = self._queries.run_query("Return patient graph context for review.", req.patient_id)
            graph_items = self._responses.sanitize_graph(
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
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            )

        return self._governance.execute(
            tool_name="patient_context_get",
            caller_role="read_only",
            request_payload=req.model_dump(),
            scope=[req.patient_id],
            fn=_handler,
        )

    def vector_evidence_search(
        self,
        question: str,
        patient_id: str = "",
        top_k: int = 5,
    ) -> dict[str, Any]:
        req = VectorEvidenceSearchRequest(question=question, patient_id=(patient_id or None), top_k=top_k)
        return self._governance.execute(
            tool_name="vector_evidence_search",
            caller_role="read_only",
            request_payload=req.model_dump(exclude_none=True),
            scope=scope_for(req.patient_id),
            fn=lambda trace_id: apply_response_budget(
                {
                    "question": req.question,
                    "vector_context": self._responses.sanitize_vector(
                        self._queries.run_query(req.question, req.patient_id, top_k=req.top_k).get("vector_context", []),
                        caller_role="read_only",
                    ),
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            ),
        )

    def graphrag_answer_generate(
        self,
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
        return self._governance.execute(
            tool_name="graphrag_answer_generate",
            caller_role="generation",
            request_payload=req.model_dump(exclude_none=True),
            scope=scope_for(req.patient_id),
            fn=lambda trace_id: self._responses.query_response(
                self._queries.run_query(style_prefix[req.response_style] + req.question, req.patient_id),
                trace_id,
                caller_role="generation",
            ),
        )

    def risk_summary_generate(
        self,
        patient_id: str,
        time_window_hours: int = 72,
    ) -> dict[str, Any]:
        req = RiskSummaryRequest(patient_id=patient_id, time_window_hours=time_window_hours)

        def _handler(trace_id: str) -> dict[str, Any]:
            prompt = f"Generate a risk summary for patient {req.patient_id} over the last {req.time_window_hours} hours using available evidence."
            result = self._queries.run_query(prompt, req.patient_id)
            risk_signals: list[str] = []
            for item in result.get("vector_context", []):
                event_type = item.get("event_type")
                if event_type and event_type not in risk_signals:
                    risk_signals.append(event_type)
            return apply_response_budget(
                {
                    "patient_id": req.patient_id,
                    "summary": truncate_text(str(result.get("answer") or ""), self._settings.max_answer_chars),
                    "risk_signals": risk_signals[: self._settings.max_context_items],
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            )

        return self._governance.execute(
            tool_name="risk_summary_generate",
            caller_role="generation",
            request_payload=req.model_dump(),
            scope=[req.patient_id],
            fn=_handler,
        )

    def evidence_bundle_export(
        self,
        question: str,
        patient_id: str = "",
        include_raw_payload: bool = False,
    ) -> dict[str, Any]:
        req = EvidenceBundleExportRequest(question=question, patient_id=(patient_id or None), include_raw_payload=include_raw_payload)

        def _handler(trace_id: str) -> dict[str, Any]:
            result = self._queries.run_query(req.question, req.patient_id)
            text_mode = vector_text_mode("export", include_raw_payload=req.include_raw_payload)
            payload = {
                "question": req.question,
                "patients": result.get("patients", []),
                "vector_context": self._responses.sanitize_vector(
                    result.get("vector_context", []),
                    caller_role="export",
                    include_raw_payload=req.include_raw_payload,
                ),
                "graph_context": self._responses.sanitize_graph(
                    result.get("graph_context", []),
                    caller_role="export",
                ),
                "answer": truncate_text(str(result.get("answer") or ""), self._settings.max_answer_chars),
                "retrieved_at": utc_timestamp(),
                "trace_id": trace_id,
                "guardrails": {
                    "evidence_text_redacted": text_mode != "bounded",
                    "evidence_access_level": text_mode,
                    "graph_access_level": "broader",
                    "raw_payload_requested": req.include_raw_payload,
                    "raw_payload_returned": False,
                    "max_response_bytes": self._settings.max_response_bytes,
                    "response_truncated": False,
                },
            }
            return apply_response_budget(payload, max_response_bytes=self._settings.max_response_bytes)

        return self._governance.execute(
            tool_name="evidence_bundle_export",
            caller_role="export",
            request_payload=req.model_dump(exclude_none=True),
            scope=scope_for(req.patient_id),
            fn=_handler,
        )

    def timeline_explain(
        self,
        patient_id: str,
        time_window_hours: int = 168,
    ) -> dict[str, Any]:
        req = TimelineExplainRequest(patient_id=patient_id, time_window_hours=time_window_hours)

        def _handler(trace_id: str) -> dict[str, Any]:
            result = self._queries.run_query(
                f"Explain timeline progression for patient {req.patient_id} across the last {req.time_window_hours} hours.",
                req.patient_id,
            )
            graph_items = self._responses.sanitize_graph(
                result.get("graph_context", []),
                caller_role="generation",
            )
            return apply_response_budget(
                {
                    "patient_id": req.patient_id,
                    "time_window_hours": req.time_window_hours,
                    "timeline_summary": truncate_text(
                        str(result.get("answer") or ""), self._settings.max_answer_chars
                    ),
                    "graph_context": graph_items,
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            )

        return self._governance.execute(
            tool_name="timeline_explain",
            caller_role="generation",
            request_payload=req.model_dump(),
            scope=[req.patient_id],
            fn=_handler,
        )

    def medication_risk_assess(self, patient_id: str) -> dict[str, Any]:
        req = MedicationRiskAssessRequest(patient_id=patient_id)

        def _handler(trace_id: str) -> dict[str, Any]:
            result = self._queries.run_query(
                f"Assess medication risk, contraindications, interactions, and adverse events for patient {req.patient_id}.",
                req.patient_id,
            )
            graph_items = result.get("graph_context", [])
            first_patient = graph_items[0] if graph_items else {}
            return apply_response_budget(
                {
                    "patient_id": req.patient_id,
                    "risk_assessment": truncate_text(
                        str(result.get("answer") or ""), self._settings.max_answer_chars
                    ),
                    "contraindications": first_patient.get("contraindications", [])[: self._settings.max_context_items],
                    "adverse_events": first_patient.get("adverse_events", [])[: self._settings.max_context_items],
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            )

        return self._governance.execute(
            tool_name="medication_risk_assess",
            caller_role="generation",
            request_payload=req.model_dump(),
            scope=[req.patient_id],
            fn=_handler,
        )

    def coding_gap_detect(
        self,
        patient_id: str,
        question: str = "Review coding and claims consistency gaps for this patient.",
    ) -> dict[str, Any]:
        req = CodingGapDetectRequest(patient_id=patient_id, question=question)

        def _handler(trace_id: str) -> dict[str, Any]:
            result = self._queries.run_query(req.question, req.patient_id)
            graph_items = result.get("graph_context", [])
            first_patient = graph_items[0] if graph_items else {}
            return apply_response_budget(
                {
                    "patient_id": req.patient_id,
                    "coding_gap_summary": truncate_text(
                        str(result.get("answer") or ""), self._settings.max_answer_chars
                    ),
                    "claims": first_patient.get("claims", [])[: self._settings.max_context_items],
                    "icd10_codes": first_patient.get("icd10_codes", [])[: self._settings.max_context_items],
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            )

        return self._governance.execute(
            tool_name="coding_gap_detect",
            caller_role="generation",
            request_payload=req.model_dump(),
            scope=[req.patient_id],
            fn=_handler,
        )

    def cohort_risk_summary(
        self,
        question: str,
        top_k: int = 5,
    ) -> dict[str, Any]:
        req = CohortRiskSummaryRequest(question=question, top_k=top_k)

        def _handler(trace_id: str) -> dict[str, Any]:
            result = self._queries.run_query(req.question, patient_id=None, top_k=req.top_k)
            return apply_response_budget(
                {
                    "question": req.question,
                    "cohort_summary": truncate_text(
                        str(result.get("answer") or ""), self._settings.max_answer_chars
                    ),
                    "patients": result.get("patients", []),
                    "vector_context": self._responses.sanitize_vector(
                        result.get("vector_context", []),
                        caller_role="generation",
                    ),
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                    "guardrails": {
                        "evidence_text_redacted": True,
                        "evidence_access_level": "none",
                        "graph_access_level": "standard",
                        "max_response_bytes": self._settings.max_response_bytes,
                        "response_truncated": False,
                    },
                }
            )

        return self._governance.execute(
            tool_name="cohort_risk_summary",
            caller_role="generation",
            request_payload=req.model_dump(),
            scope="cohort",
            fn=_handler,
        )

    def skills_plan_get(
        self,
        business_goal: str,
        agent: str = "",
    ) -> dict[str, Any]:
        req = SkillsPlanRequest(business_goal=business_goal, agent=(agent or None))

        def _handler(trace_id: str) -> dict[str, Any]:
            return apply_response_budget(
                {
                    **build_skill_plan(
                        self._load_skills(str(self._settings.skills_layer_path)),
                        business_goal=req.business_goal,
                        agent=req.agent,
                    ),
                    "retrieved_at": utc_timestamp(),
                    "trace_id": trace_id,
                }
            )

        return self._governance.execute(
            tool_name="skills_plan_get",
            caller_role="read_only",
            request_payload=req.model_dump(exclude_none=True),
            scope="none",
            fn=_handler,
        )
