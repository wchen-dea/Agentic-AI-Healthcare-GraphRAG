"""Prometheus metrics shared by agent services.

Metric names are an operations contract (dashboards and alerts depend on them)
and use the ``agent_service_`` prefix. Requires the ``agent-core[metrics]``
extra, which keeps the base package free of exporter dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import REGISTRY, CollectorRegistry, Counter, Histogram

METRIC_PREFIX = "agent_service_"


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
                f"{METRIC_PREFIX}http_request_duration_seconds",
                "HTTP request latency in seconds",
                ["method", "path", "status"],
                registry=registry,
            ),
            tool_execution_duration_seconds=Histogram(
                f"{METRIC_PREFIX}tool_execution_duration_seconds",
                "Tool execution latency in seconds",
                ["tool", "outcome"],
                registry=registry,
            ),
            tool_execution_total=Counter(
                f"{METRIC_PREFIX}tool_execution_total",
                "Tool execution count",
                ["tool", "outcome"],
                registry=registry,
            ),
            audit_write_failures_total=Counter(
                f"{METRIC_PREFIX}audit_write_failures_total",
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

    def record_audit_failure(self, tool_name: str) -> None:
        self.audit_write_failures_total.labels(tool=tool_name).inc()

    def observe_http(self, method: str, path: str, status: int, elapsed_seconds: float) -> None:
        self.http_request_duration_seconds.labels(method=method, path=path, status=str(status)).observe(
            max(elapsed_seconds, 0.0)
        )
