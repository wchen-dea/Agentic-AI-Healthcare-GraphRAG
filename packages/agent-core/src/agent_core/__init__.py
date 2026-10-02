"""Provider-neutral contracts shared by every domain agent service (ADR-0012).

Modules:
- ``ports``: storage, LLM, session-memory, and tracing interfaces.
- ``runtime``: the capability bundle the orchestrator is allowed to call.
- ``guardrails``: guardrail result type and domain-neutral checks.
- ``policy``: role-based tool authorization.
- ``governance``: authorize, run, audit, and measure tool calls.
- ``metrics``: Prometheus service metrics (``agent-core[metrics]`` extra).
- ``audit``: audit events and sinks.
- ``streaming``: server-sent event (SSE) contract.
- ``settings``: typed base settings for agent services.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
