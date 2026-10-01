"""Prometheus metrics for the agent service.

Metric names are an operations contract (dashboards and alerts depend on them)
and keep the ``rag_api_`` prefix until the infra rename in ADR-0012 Phase 3.
"""
from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram


@dataclass(frozen=True)
class ServiceMetrics:
    http_request_duration_seconds: Histogram
    tool_execution_duration_seconds: Histogram
    tool_execution_total: Counter
    audit_write_failures_total: Counter

    @classmethod
    def register(cls, registry: CollectorRegistry = REGISTRY) -> ServiceMetrics:
        return cls(
            http_request_duration_seconds=Histogram(
                "rag_api_http_request_duration_seconds",
                "HTTP request latency in seconds",
                ["method", "path", "status"],
                registry=registry,
            ),
            tool_execution_duration_seconds=Histogram(
                "rag_api_tool_execution_duration_seconds",
                "Tool execution latency in seconds",
                ["tool", "outcome"],
                registry=registry,
            ),
            tool_execution_total=Counter(
                "rag_api_tool_execution_total",
                "Tool execution count",
                ["tool", "outcome"],
                registry=registry,
            ),
            audit_write_failures_total=Counter(
                "rag_api_audit_write_failures_total",
                "Audit events that could not be persisted",
                ["tool"],
                registry=registry,
            ),
        )

    def observe_tool(self, tool_name: str, outcome: str, elapsed_seconds: float) -> None:
        self.tool_execution_duration_seconds.labels(tool=tool_name, outcome=outcome).observe(
            max(elapsed_seconds, 0.0)
        )
        self.tool_execution_total.labels(tool=tool_name, outcome=outcome).inc()
