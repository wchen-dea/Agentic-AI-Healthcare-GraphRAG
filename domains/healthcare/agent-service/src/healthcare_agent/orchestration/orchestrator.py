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
from healthcare_agent.orchestration.memory import PatientMemoryRecord


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
        # Completed runs remain checkpointed for audit, time travel, and
        # controlled state editing. Pending-review eviction is still bounded
        # and releases its thread in ``PendingReviews``.
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

    def history(self, thread_id: str, *, limit: int = 100) -> list[Any]:
        """Return checkpoint history, newest first."""
        if not 1 <= limit <= 500:
            raise ValueError("limit must be between 1 and 500")
        return list(self._graph.get_state_history(_run_config(None, thread_id=thread_id), limit=limit))

    def state(self, thread_id: str, *, checkpoint_id: str | None = None) -> Any:
        """Read the latest state or a selected historical checkpoint."""
        config = _run_config(None, thread_id=thread_id)
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id
        return self._graph.get_state(config)

    def edit_state(self, thread_id: str, values: dict[str, Any], *, checkpoint_id: str | None = None) -> Any:
        """Apply a controlled delta without allowing identity or trace edits."""
        if not values:
            raise ValueError("values must be a non-empty object")
        allowed = {"structured", "session_context", "context_limit", "patient_memory_policy"}
        forbidden = set(values) - allowed
        if forbidden:
            raise ValueError(f"state fields are not editable: {sorted(forbidden)}")
        config = _run_config(None, thread_id=thread_id)
        if checkpoint_id:
            config["configurable"]["checkpoint_id"] = checkpoint_id
        return self._graph.update_state(config, values)

    def rewind(self, thread_id: str, checkpoint_id: str) -> Any:
        """Select a historical checkpoint for inspection or subsequent editing."""
        snapshot = self.state(thread_id, checkpoint_id=checkpoint_id)
        if snapshot is None:
            raise KeyError(checkpoint_id)
        return snapshot

    def resume_from_checkpoint(self, thread_id: str, checkpoint_id: str) -> dict[str, Any]:
        """Resume execution from a selected checkpoint."""
        snapshot = self.rewind(thread_id, checkpoint_id)
        values = getattr(snapshot, "values", {})
        config = _run_config(None, thread_id=thread_id)
        config["configurable"]["checkpoint_id"] = checkpoint_id
        final_state = self._graph.invoke(None, config=config)
        return self._finish(str(values.get("question") or ""), final_state, thread_id, extract_interrupt(final_state))

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
