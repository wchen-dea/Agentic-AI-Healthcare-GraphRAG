"""Governed tool execution: authorize, run, audit, and measure every call.

Authorization is deterministic and runs before the tool body. Every outcome,
including denials and client cancellations, produces one audit event.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Any

from agent_core.audit import AuditEvent, JsonlAuditSink, hash_payload
from agent_core.policy import AuthorizationError, ToolPolicy

from healthcare_agent.config.settings import HealthcareAgentSettings
from healthcare_agent.observability.metrics import ServiceMetrics

logger = logging.getLogger("healthcare_agent")

PatientScope = list[str] | str


def patient_scope(patient_id: str | None) -> PatientScope:
    return [patient_id] if patient_id else "cohort"


@lru_cache(maxsize=4)
def load_policy(path: str) -> ToolPolicy:
    return ToolPolicy.load(path)


class ToolGovernance:
    def __init__(self, settings: HealthcareAgentSettings, metrics: ServiceMetrics) -> None:
        self._settings = settings
        self._metrics = metrics
        self._sink = JsonlAuditSink(settings.audit_log_path, on_failure=self._on_audit_failure)

    def _on_audit_failure(self, event: AuditEvent, exc: Exception) -> None:
        # Requests continue, but a lost audit event must be visible to operators.
        self._metrics.audit_write_failures_total.labels(tool=event.tool_name).inc()
        logger.error("audit write failed trace_id=%s tool=%s: %s", event.trace_id, event.tool_name, exc)

    def resolve_caller_role(self, header_value: str | None) -> str:
        """Honor the role header only when allowed (dev); production uses the default role."""
        if self._settings.allow_role_header and header_value:
            return header_value
        return self._settings.default_caller_role

    def authorize(self, *, tool_name: str, caller_role: str) -> str:
        return load_policy(str(self._settings.tool_policy_path)).authorize(
            tool_name=tool_name, caller_role=caller_role
        )

    def audit(
        self,
        *,
        tool_name: str,
        caller_id: str,
        request_payload: dict[str, Any],
        patient_scope: PatientScope,
        outcome: str,
        started_at: float,
        response_size_bytes: int,
        trace_id: str,
        error: str | None = None,
    ) -> None:
        self._sink.write(
            AuditEvent(
                trace_id=trace_id,
                tool_name=tool_name,
                caller_id=caller_id,
                input_hash=hash_payload(request_payload),
                patient_scope=patient_scope,
                outcome=outcome,
                latency_ms=int((time.time() - started_at) * 1000),
                response_size_bytes=response_size_bytes,
                error=error,
            )
        )

    def authorize_or_audit_denial(
        self,
        *,
        tool_name: str,
        caller_role: str,
        request_payload: dict[str, Any],
        patient_scope: PatientScope,
        started_at: float,
        trace_id: str,
    ) -> str:
        """Authorize the caller; on denial write a ``denied`` audit event and re-raise."""
        try:
            return self.authorize(tool_name=tool_name, caller_role=caller_role)
        except AuthorizationError:
            self.audit(
                tool_name=tool_name,
                caller_id=f"role:{caller_role}",
                request_payload=request_payload,
                patient_scope=patient_scope,
                outcome="denied",
                started_at=started_at,
                response_size_bytes=0,
                trace_id=trace_id,
                error=f"unauthorized: role '{caller_role}' for tool '{tool_name}'",
            )
            raise

    def observe(self, tool_name: str, outcome: str, started_at: float) -> None:
        self._metrics.observe_tool(tool_name, outcome, time.time() - started_at)

    def execute(
        self,
        *,
        tool_name: str,
        caller_role: str,
        request_payload: dict[str, Any],
        patient_scope: PatientScope,
        fn: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        """Run ``fn(trace_id)`` under policy, audit, and metrics."""
        started_at = time.time()
        trace_id = str(uuid.uuid4())
        outcome = "error"
        caller_id = self.authorize_or_audit_denial(
            tool_name=tool_name,
            caller_role=caller_role,
            request_payload=request_payload,
            patient_scope=patient_scope,
            started_at=started_at,
            trace_id=trace_id,
        )
        try:
            response = fn(trace_id)
            outcome = "success"
            self.audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request_payload,
                patient_scope=patient_scope,
                outcome=outcome,
                started_at=started_at,
                response_size_bytes=len(json.dumps(response, separators=(",", ":")).encode("utf-8")),
                trace_id=trace_id,
            )
            return response
        except Exception as exc:
            self.audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request_payload,
                patient_scope=patient_scope,
                outcome=outcome,
                started_at=started_at,
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(exc),
            )
            raise
        finally:
            self.observe(tool_name, outcome, started_at)
