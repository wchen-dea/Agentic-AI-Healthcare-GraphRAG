"""Application-facing LangGraph orchestration facade.

The facade owns a compiled graph and keeps transport/application services
independent from LangGraph implementation details. A compiled graph can be
injected in tests or at composition time; the default uses the process-wide
cached healthcare graph.

Every run gets a ``thread_id``. When human-in-the-loop review is enabled and
the graph pauses at ``human_review``, the run returns
``status="pending_approval"`` and can be continued with :meth:`resume`.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Literal, Protocol, cast

from healthcare_agent.orchestration.memory import PatientMemoryRecord
from uuid import uuid4

from langgraph.types import Command

from healthcare_agent.orchestration.graph import (
    DEFAULT_CONTEXT_LIMIT,
    _initial_state,
    _run_config,
    final_state_to_response,
    public_step,
)
from healthcare_agent.orchestration.hitl import (
    extract_interrupt,
    pending_reviews,
    release_thread,
)


class CompiledGraph(Protocol):
    def invoke(self, input: Any, *, config: dict[str, Any]) -> dict[str, Any]:
        ...

    def stream(
        self,
        input: Any,
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
        from healthcare_agent.orchestration.graph import get_compiled_graph

        return cls(get_compiled_graph())

    @property
    def _checkpointer(self) -> Any:
        return getattr(self._graph, "checkpointer", None)

    def _finish(
        self,
        question: str,
        final_state: dict[str, Any],
        thread_id: str,
        interrupt_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if interrupt_payload is not None and self._checkpointer is not None:
            pending_reviews.add(thread_id, interrupt_payload, self._checkpointer)
            return final_state_to_response(
                question, final_state, thread_id=thread_id, pending_review=interrupt_payload
            )
        release_thread(self._checkpointer, thread_id)
        return final_state_to_response(question, final_state, thread_id=thread_id)

    def run(
        self,
        question: str,
        patient_id: str | None = None,
        *,
        structured: bool = False,
        session_context: str = "",
        patient_memory: PatientMemoryRecord | None = None,
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> dict[str, Any]:
        thread_id = uuid4().hex
        final_state = self._graph.invoke(
            cast(
                dict[str, Any],
                _initial_state(
                    question,
                    patient_id,
                    structured=structured,
                    session_context=session_context,
                    patient_memory=patient_memory,
                    context_limit=context_limit,
                ),
            ),
            config=_run_config(patient_id, thread_id=thread_id),
        )
        return self._finish(question, final_state, thread_id, extract_interrupt(final_state))

    def stream(
        self,
        question: str,
        patient_id: str | None = None,
        *,
        structured: bool = False,
        session_context: str = "",
        patient_memory: PatientMemoryRecord | None = None,
        context_limit: int = DEFAULT_CONTEXT_LIMIT,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        thread_id = uuid4().hex
        final_state: dict[str, Any] = {}
        interrupt_payload: dict[str, Any] | None = None
        for mode, chunk in self._graph.stream(
            cast(
                dict[str, Any],
                _initial_state(
                    question,
                    patient_id,
                    structured=structured,
                    session_context=session_context,
                    patient_memory=patient_memory,
                    context_limit=context_limit,
                ),
            ),
            config=_run_config(patient_id, thread_id=thread_id),
            stream_mode=["updates", "values"],
        ):
            if mode == "updates":
                payload = extract_interrupt(chunk)
                if payload is not None:
                    interrupt_payload = payload
                for node, update in chunk.items():
                    yield "step", public_step(node, update)
            elif mode == "values":
                final_state = chunk
        yield "result", self._finish(question, final_state, thread_id, interrupt_payload)

    def pending(self, thread_id: str) -> dict[str, Any] | None:
        """Return the interrupt payload for a paused thread, if any."""
        return pending_reviews.get(thread_id)

    def resume(
        self,
        thread_id: str,
        decision: Literal["approve", "reject"],
        note: str | None = None,
    ) -> dict[str, Any]:
        """Continue a paused run with a reviewer decision.

        Raises ``KeyError`` when the thread is unknown, already resumed, or
        evicted from the pending registry.
        """
        payload = pending_reviews.pop(thread_id)
        if payload is None:
            raise KeyError(thread_id)
        patient_id = payload.get("patient_id")
        question = str(payload.get("question") or "")
        try:
            final_state = self._graph.invoke(
                Command(resume={"decision": decision, "note": note or ""}),
                config=_run_config(patient_id, thread_id=thread_id),
            )
        except Exception:
            release_thread(self._checkpointer, thread_id)
            raise
        return self._finish(question, final_state, thread_id, extract_interrupt(final_state))
