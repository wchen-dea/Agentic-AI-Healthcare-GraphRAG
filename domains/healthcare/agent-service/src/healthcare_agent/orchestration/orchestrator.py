"""Application-facing LangGraph orchestration facade.

The facade owns a compiled graph and keeps transport/application services
independent from LangGraph implementation details. A compiled graph can be
injected in tests or at composition time; the default preserves the existing
healthcare graph behavior.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, cast

from healthcare_agent.orchestration.graph import (
    DEFAULT_CONTEXT_LIMIT,
    _initial_state,
    _run_config,
    final_state_to_response,
    public_step,
)


class CompiledGraph(Protocol):
    def invoke(self, input: dict[str, Any], *, config: dict[str, Any]) -> dict[str, Any]:
        ...

    def stream(
        self,
        input: dict[str, Any],
        *,
        config: dict[str, Any],
        stream_mode: list[str],
    ) -> Iterator[tuple[str, Any]]:
        ...


class LangGraphOrchestrator:
    """Stable application port for synchronous and streaming graph execution."""

    def __init__(self, graph: CompiledGraph) -> None:
        self._graph = graph

    @classmethod
    def build(cls) -> "LangGraphOrchestrator":
        from healthcare_agent.orchestration.graph import build_healthcare_graph

        return cls(build_healthcare_graph())

    def run(
        self,
        question: str,
        patient_id: str | None = None,
        *,
        structured: bool = False,
        session_context: str = "",
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> dict[str, Any]:
        final_state = self._graph.invoke(
            cast(
                dict[str, Any],
                _initial_state(
                    question,
                    patient_id,
                    structured=structured,
                    session_context=session_context,
                    context_limit=context_limit,
                ),
            ),
            config=_run_config(patient_id),
        )
        return final_state_to_response(question, final_state)

    def stream(
        self,
        question: str,
        patient_id: str | None = None,
        *,
        structured: bool = False,
        session_context: str = "",
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        final_state: dict[str, Any] = {}
        for mode, chunk in self._graph.stream(
            cast(
                dict[str, Any],
                _initial_state(
                    question,
                    patient_id,
                    structured=structured,
                    session_context=session_context,
                    context_limit=context_limit,
                ),
            ),
            config=_run_config(patient_id),
            stream_mode=["updates", "values"],
        ):
            if mode == "updates":
                for node, update in chunk.items():
                    yield "step", public_step(node, update)
            elif mode == "values":
                final_state = chunk
        yield "result", final_state_to_response(question, final_state)