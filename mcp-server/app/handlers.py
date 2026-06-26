from __future__ import annotations

import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from .audit import write_audit_event
from .auth import authorize
from .clients.rag_api_client import RagApiClient
from .config import Settings
from .schemas import validate_request, validate_response


class MCPHandlers:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.rag = RagApiClient(settings.rag_api_base_url, settings.rag_api_timeout_seconds)

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(data).hexdigest()

    def _audit(
        self,
        *,
        tool_name: str,
        caller_id: str,
        request_payload: dict,
        patient_scope: list[str] | str,
        outcome: str,
        latency_ms: int,
        response_size_bytes: int,
        trace_id: str,
        error: str | None = None,
    ) -> None:
        event = {
            "timestamp": self._ts(),
            "trace_id": trace_id,
            "tool_name": tool_name,
            "caller_id": caller_id,
            "input_hash": self._hash_payload(request_payload),
            "patient_scope": patient_scope,
            "outcome": outcome,
            "latency_ms": latency_ms,
            "response_size_bytes": response_size_bytes,
        }
        if error:
            event["error"] = error
        write_audit_event(self.settings.audit_log_path, event)

    def _authorize(self, tool_name: str, caller_role: str, auth_token: str | None) -> str:
        return authorize(
            tool_name=tool_name,
            caller_role=caller_role,
            auth_token=auth_token,
            require_auth=self.settings.require_auth,
            expected_token=self.settings.api_token,
            policy_path=str(self.settings.tool_policy_path),
        )

    def patient_context_get(
        self,
        request: dict,
        *,
        auth_token: str | None,
        caller_role: str = "read_only",
    ) -> dict:
        tool_name = "patient_context_get"
        start = time.time()
        trace_id = str(uuid.uuid4())
        caller_id = self._authorize(tool_name, caller_role, auth_token)
        validate_request(tool_name, request)

        try:
            result = self.rag.query(
                question="Return patient graph context for review.",
                patient_id=request["patient_id"],
            )
            graph_context = result.get("graph_context", [])
            if not request.get("include_claims", True):
                for item in graph_context:
                    item.pop("claims", None)
            if not request.get("include_interactions", True):
                for item in graph_context:
                    item.pop("interactions", None)

            response = {
                "patient_id": request["patient_id"],
                "graph_context": graph_context,
                "retrieved_at": self._ts(),
                "trace_id": trace_id,
            }
            validate_response(tool_name, response)
            payload_size = len(json.dumps(response).encode("utf-8"))
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=[request["patient_id"]],
                outcome="success",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=payload_size,
                trace_id=trace_id,
            )
            return response
        except Exception as ex:
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=[request["patient_id"]],
                outcome="error",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(ex),
            )
            raise

    def vector_evidence_search(
        self,
        request: dict,
        *,
        auth_token: str | None,
        caller_role: str = "read_only",
    ) -> dict:
        tool_name = "vector_evidence_search"
        start = time.time()
        trace_id = str(uuid.uuid4())
        caller_id = self._authorize(tool_name, caller_role, auth_token)
        validate_request(tool_name, request)

        try:
            result = self.rag.query(
                question=request["question"],
                patient_id=request.get("patient_id"),
            )
            top_k = request.get("top_k", 5)
            response = {
                "question": request["question"],
                "vector_context": result.get("vector_context", [])[:top_k],
                "retrieved_at": self._ts(),
                "trace_id": trace_id,
            }
            validate_response(tool_name, response)
            payload_size = len(json.dumps(response).encode("utf-8"))
            patient_scope = (
                [request["patient_id"]] if request.get("patient_id") else "cohort"
            )
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=patient_scope,
                outcome="success",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=payload_size,
                trace_id=trace_id,
            )
            return response
        except Exception as ex:
            patient_scope = (
                [request["patient_id"]] if request.get("patient_id") else "cohort"
            )
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=patient_scope,
                outcome="error",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(ex),
            )
            raise

    def graphrag_answer_generate(
        self,
        request: dict,
        *,
        auth_token: str | None,
        caller_role: str = "generation",
    ) -> dict:
        tool_name = "graphrag_answer_generate"
        start = time.time()
        trace_id = str(uuid.uuid4())
        caller_id = self._authorize(tool_name, caller_role, auth_token)
        validate_request(tool_name, request)

        style_prefix = {
            "concise": "Answer concisely. ",
            "clinical": "Use clinically oriented language. ",
            "audit": "Include evidence traceability details. ",
        }
        question = style_prefix.get(request.get("response_style", "concise"), "") + request[
            "question"
        ]

        try:
            result = self.rag.query(question=question, patient_id=request.get("patient_id"))
            response = {
                "answer": result.get("answer", ""),
                "patients": result.get("patients", []),
                "vector_context": result.get("vector_context", []),
                "graph_context": result.get("graph_context", []),
                "retrieved_at": self._ts(),
                "trace_id": trace_id,
            }
            validate_response(tool_name, response)
            payload_size = len(json.dumps(response).encode("utf-8"))
            patient_scope = (
                [request["patient_id"]] if request.get("patient_id") else "cohort"
            )
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=patient_scope,
                outcome="success",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=payload_size,
                trace_id=trace_id,
            )
            return response
        except Exception as ex:
            patient_scope = (
                [request["patient_id"]] if request.get("patient_id") else "cohort"
            )
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=patient_scope,
                outcome="error",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(ex),
            )
            raise

    def risk_summary_generate(
        self,
        request: dict,
        *,
        auth_token: str | None,
        caller_role: str = "generation",
    ) -> dict:
        tool_name = "risk_summary_generate"
        start = time.time()
        trace_id = str(uuid.uuid4())
        caller_id = self._authorize(tool_name, caller_role, auth_token)
        validate_request(tool_name, request)

        prompt = (
            f"Generate a risk summary for patient {request['patient_id']} "
            f"over the last {request.get('time_window_hours', 72)} hours using available evidence."
        )

        try:
            result = self.rag.query(question=prompt, patient_id=request["patient_id"])
            vector_context = result.get("vector_context", [])
            risk_signals = []
            for item in vector_context:
                event_type = item.get("event_type")
                if event_type and event_type not in risk_signals:
                    risk_signals.append(event_type)

            response = {
                "patient_id": request["patient_id"],
                "summary": result.get("answer", ""),
                "risk_signals": risk_signals,
                "retrieved_at": self._ts(),
                "trace_id": trace_id,
            }
            validate_response(tool_name, response)
            payload_size = len(json.dumps(response).encode("utf-8"))
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=[request["patient_id"]],
                outcome="success",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=payload_size,
                trace_id=trace_id,
            )
            return response
        except Exception as ex:
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=[request["patient_id"]],
                outcome="error",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(ex),
            )
            raise

    def evidence_bundle_export(
        self,
        request: dict,
        *,
        auth_token: str | None,
        caller_role: str = "export",
    ) -> dict:
        tool_name = "evidence_bundle_export"
        start = time.time()
        trace_id = str(uuid.uuid4())
        caller_id = self._authorize(tool_name, caller_role, auth_token)
        validate_request(tool_name, request)

        try:
            result = self.rag.query(
                question=request["question"],
                patient_id=request.get("patient_id"),
            )
            vector_evidence = result.get("vector_context", [])
            if not request.get("include_raw_payload", False):
                for item in vector_evidence:
                    item.pop("payload", None)

            response = {
                "question": request["question"],
                "bundle": {
                    "vector_evidence": vector_evidence,
                    "graph_evidence": result.get("graph_context", []),
                },
                "retrieved_at": self._ts(),
                "trace_id": trace_id,
            }
            validate_response(tool_name, response)
            payload_size = len(json.dumps(response).encode("utf-8"))
            patient_scope = (
                [request["patient_id"]] if request.get("patient_id") else "cohort"
            )
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=patient_scope,
                outcome="success",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=payload_size,
                trace_id=trace_id,
            )
            return response
        except Exception as ex:
            patient_scope = (
                [request["patient_id"]] if request.get("patient_id") else "cohort"
            )
            self._audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request,
                patient_scope=patient_scope,
                outcome="error",
                latency_ms=int((time.time() - start) * 1000),
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(ex),
            )
            raise
