"""Capability bundle the orchestration layer may invoke (ADR-0010, ADR-0012).

The composition root of each domain service builds an ``AgentRuntime`` from
its adapters. Authorization happens before any capability is invoked.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class VectorSearchFn(Protocol):
    def __call__(self, query_text: str, patient_id: str | None, limit: int) -> list[dict[str, Any]]: ...


class GraphSearchFn(Protocol):
    def __call__(self, patient_ids: list[str]) -> list[dict[str, Any]]: ...


class SynthesizeFn(Protocol):
    def __call__(
        self,
        question: str,
        vector_ctx: list[dict[str, Any]],
        graph_ctx: list[dict[str, Any]],
    ) -> str: ...


class StructuredSynthesizeFn(Protocol):
    def __call__(
        self,
        question: str,
        vector_ctx: list[dict[str, Any]],
        graph_ctx: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class AgentRuntime:
    """Capabilities the orchestrator may use. Authorization happens before invocation."""

    vector_search: VectorSearchFn
    graph_search: GraphSearchFn
    synthesize: SynthesizeFn
    synthesize_structured: StructuredSynthesizeFn | None = None
