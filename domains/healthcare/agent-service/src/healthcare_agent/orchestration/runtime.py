"""Tool gateway port for the LangGraph orchestration layer (ADR-0010).

Agent nodes depend on this port instead of importing the composition root
(``app``). Today the composition root binds in-process adapters over Qdrant,
Neo4j, and the LLM provider; a later phase binds MCP-client adapters that call
the per-domain MCP servers without changing any agent node.

The runtime contract lives in ``agent_core.runtime`` (ADR-0012); this module
keeps the process-wide binding for the healthcare service.
"""
from __future__ import annotations

from agent_core.runtime import (
    AgentRuntime,
    GraphSearchFn,
    StructuredSynthesizeFn,
    SynthesizeFn,
    VectorSearchFn,
)

__all__ = [
    "AgentRuntime",
    "GraphSearchFn",
    "StructuredSynthesizeFn",
    "SynthesizeFn",
    "VectorSearchFn",
    "configure_runtime",
    "get_runtime",
]

_runtime: AgentRuntime | None = None


def configure_runtime(runtime: AgentRuntime | None) -> None:
    """Bind (or clear, with ``None``) the process-wide agent runtime."""
    global _runtime
    _runtime = runtime


def get_runtime() -> AgentRuntime:
    """Return the bound runtime, lazily binding the in-process adapters."""
    if _runtime is None:
        # The composition root binds the runtime on import.
        import healthcare_agent.main  # noqa: F401

    if _runtime is None:
        raise RuntimeError("Agent runtime is not configured.")
    return _runtime
