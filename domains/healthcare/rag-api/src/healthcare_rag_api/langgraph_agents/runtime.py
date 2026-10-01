"""Tool gateway port for the LangGraph orchestration layer (ADR-0010).

Agent nodes depend on this port instead of importing the composition root
(``app``). Today the composition root binds in-process adapters over Qdrant,
Neo4j, and the LLM provider; a later phase binds MCP-client adapters that call
the per-domain MCP servers without changing any agent node.
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


_runtime: AgentRuntime | None = None


def configure_runtime(runtime: AgentRuntime | None) -> None:
    """Bind (or clear, with ``None``) the process-wide agent runtime."""
    global _runtime
    _runtime = runtime


def get_runtime() -> AgentRuntime:
    """Return the bound runtime, lazily binding the in-process adapters."""
    if _runtime is None:
        # The composition root binds the runtime on import.
        import healthcare_rag_api.app  # noqa: F401

    if _runtime is None:
        raise RuntimeError("Agent runtime is not configured.")
    return _runtime
