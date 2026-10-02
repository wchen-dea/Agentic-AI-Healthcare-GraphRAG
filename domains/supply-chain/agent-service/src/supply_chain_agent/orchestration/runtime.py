"""Tool gateway port for the supply-chain LangGraph orchestration (ADR-0010).

Agent nodes depend on this port instead of importing the composition root.
The runtime contract lives in ``agent_core.runtime`` (ADR-0012); this module
keeps the process-wide binding for the supply-chain service.
"""
from __future__ import annotations

from agent_core.runtime import AgentRuntime, GraphSearchFn, SynthesizeFn, VectorSearchFn

__all__ = ["AgentRuntime", "GraphSearchFn", "SynthesizeFn", "VectorSearchFn", "configure_runtime", "get_runtime"]

_runtime: AgentRuntime | None = None


def configure_runtime(runtime: AgentRuntime | None) -> None:
    """Bind (or clear, with ``None``) the process-wide agent runtime."""
    global _runtime
    _runtime = runtime


def get_runtime() -> AgentRuntime:
    """Return the bound runtime, lazily binding the in-process adapters."""
    if _runtime is None:
        # The composition root binds the runtime on import.
        import supply_chain_agent.main  # noqa: F401

    if _runtime is None:
        raise RuntimeError("Agent runtime is not configured.")
    return _runtime
