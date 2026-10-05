"""Governed tool execution: authorize, run, audit, and measure every call.

Authorization is deterministic and runs before the tool body. Every outcome,
including denials and failures, produces one audit event. Transports (HTTP
routes, MCP tools) call ``ToolGovernance``; they never call tools directly.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Any, Protocol

from agent_core.audit import AuditEvent, JsonlAuditSink, hash_payload
from agent_core.policy import AuthorizationError, ToolPolicy
from agent_core.settings import AgentServiceSettings

logger = logging.getLogger(__name__)

Scope = list[str] | str


class GovernanceMetrics(Protocol):
    def observe_tool(self, tool_name: str, outcome: str, elapsed_seconds: float) -> None: ...

    def record_audit_failure(self, tool_name: str) -> None: ...


def scope_for(subject_id: str | None, *, collective: str = "cohort") -> Scope:
    """Scope of one subject, or ``collective`` when the call spans many."""
    return [subject_id] if subject_id else collective


@lru_cache(maxsize=4)
def load_policy(path: str) -> ToolPolicy:
    return ToolPolicy.load(path)


class ToolGovernance:
    def __init__(
        self,
        settings: AgentServiceSettings,
        metrics: GovernanceMetrics,
        *,
        audit_scope_key: str = "scope",
    ) -> None:
        self._settings = settings
        self._metrics = metrics
        self._sink = JsonlAuditSink(
            settings.audit_log_path, on_failure=self._on_audit_failure, scope_key=audit_scope_key
        )

    def _on_audit_failure(self, event: AuditEvent, exc: Exception) -> None:
        # The caller decides whether this failure is fail-open or fail-closed.
        self._metrics.record_audit_failure(event.tool_name)
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
        scope: Scope,
        outcome: str,
        started_at: float,
        response_size_bytes: int,
        trace_id: str,
        error: str | None = None,
    ) -> bool:
        return self._sink.write(
            AuditEvent(
                trace_id=trace_id,
                tool_name=tool_name,
                caller_id=caller_id,
                input_hash=hash_payload(request_payload),
                scope=scope,
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
        scope: Scope,
        started_at: float,
        trace_id: str,
    ) -> str:
        """Authorize the caller; on denial write a ``denied`` audit event and re-raise."""
        try:
            return self.authorize(tool_name=tool_name, caller_role=caller_role)
        except AuthorizationError:
            if not self.audit(
                tool_name=tool_name,
                caller_id=f"role:{caller_role}",
                request_payload=request_payload,
                scope=scope,
                outcome="denied",
                started_at=started_at,
                response_size_bytes=0,
                trace_id=trace_id,
                error=f"unauthorized: role '{caller_role}' for tool '{tool_name}'",
            ) and self._settings.audit_fail_closed:
                raise RuntimeError("Audit sink unavailable; authorization denied closed")
            raise

    def observe(self, tool_name: str, outcome: str, started_at: float) -> None:
        self._metrics.observe_tool(tool_name, outcome, time.time() - started_at)

    def execute(
        self,
        *,
        tool_name: str,
        caller_role: str,
        request_payload: dict[str, Any],
        scope: Scope,
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
            scope=scope,
            started_at=started_at,
            trace_id=trace_id,
        )
        try:
            response = fn(trace_id)
            outcome = "success"
            audit_ok = self.audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request_payload,
                scope=scope,
                outcome=outcome,
                started_at=started_at,
                response_size_bytes=len(json.dumps(response, separators=(",", ":")).encode("utf-8")),
                trace_id=trace_id,
            )
            if not audit_ok and self._settings.audit_fail_closed:
                raise RuntimeError("Audit sink unavailable; privileged operation denied closed")
            return response
        except Exception as exc:
            audit_ok = self.audit(
                tool_name=tool_name,
                caller_id=caller_id,
                request_payload=request_payload,
                scope=scope,
                outcome=outcome,
                started_at=started_at,
                response_size_bytes=0,
                trace_id=trace_id,
                error=str(exc),
            )
            if not audit_ok and self._settings.audit_fail_closed:
                raise RuntimeError("Audit sink unavailable; operation denied closed") from exc
            raise
        finally:
            self.observe(tool_name, outcome, started_at)


__all__ = [
    "AuthorizationError",
    "GovernanceMetrics",
    "Scope",
    "ToolGovernance",
    "load_policy",
    "scope_for",
]
