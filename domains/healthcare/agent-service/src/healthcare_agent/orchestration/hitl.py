"""Human-in-the-loop (HITL) review for the healthcare LangGraph.

When ``HITL_ENABLED`` is truthy the graph is compiled with a checkpointer and
a ``human_review`` node that pauses (``langgraph.types.interrupt``) before
synthesis for medication-safety requests or low-confidence evidence. The
paused run is persisted per ``thread_id`` until a reviewer resumes it with an
approve/reject decision.

Conversation memory stays in ``SessionStore``; the checkpointer only holds
in-flight graph state for paused runs and is cleared once a run completes.

The default ``InMemorySaver`` is process-local: use a shared checkpointer
(for example Postgres or Redis) when running more than one replica.
"""
from __future__ import annotations

import os
import threading
from collections import OrderedDict
from contextlib import AbstractContextManager
from functools import lru_cache
from typing import Any

from langgraph.types import interrupt

from healthcare_agent.orchestration.state import HealthcareAgentState

_TRUTHY = {"1", "true", "yes", "on"}
REJECTED_ANSWER = "Response declined by clinical reviewer."
PENDING_ANSWER = "Pending clinician review."


def hitl_enabled() -> bool:
    return os.getenv("HITL_ENABLED", "").strip().lower() in _TRUTHY


def review_confidence_threshold() -> float:
    try:
        return max(0.0, min(float(os.getenv("HITL_CONFIDENCE_THRESHOLD", "0.75")), 1.0))
    except (TypeError, ValueError):
        return 0.75


def _max_pending() -> int:
    try:
        return max(1, int(os.getenv("HITL_MAX_PENDING", "1000")))
    except (TypeError, ValueError):
        return 1000


@lru_cache(maxsize=1)
def get_checkpointer() -> Any:
    uri = os.getenv("LANGGRAPH_CHECKPOINT_POSTGRES_URI", "").strip()
    if uri:
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            context: AbstractContextManager[Any] = PostgresSaver.from_conn_string(uri)
            saver = context.__enter__()
            saver.setup()
            setattr(saver, "_healthcare_connection_context", context)
            return saver
        except Exception:
            if os.getenv("LANGGRAPH_CHECKPOINT_REQUIRED", "").strip().lower() in _TRUTHY:
                raise

    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


# ── Review node ─────────────────────────────────────────────────────────────

def review_reason(state: HealthcareAgentState) -> str | None:
    if state.get("request_type") == "medication_safety":
        return "medication_safety"
    if float(state.get("confidence", 0.0)) < review_confidence_threshold():
        return "low_confidence"
    return None


def human_review(state: HealthcareAgentState) -> dict[str, Any]:
    """Pause for clinician approval when the request needs review.

    The interrupt payload carries counts and routing metadata only, never raw
    evidence, so the pending response does not widen PHI exposure.
    """
    reason = review_reason(state)
    if reason is None:
        return {
            "review_required": False,
            "messages": [{"agent": "human_review", "action": "skip"}],
        }

    decision = interrupt({
        "reason": reason,
        "question": state.get("question", ""),
        "patient_id": state.get("patient_id"),
        "request_type": state.get("request_type", "patient_summary"),
        "confidence": float(state.get("confidence", 0.0)),
        "evidence_counts": {
            "vector": len(state.get("vector_context") or []),
            "graph": len(state.get("graph_context") or []),
        },
    })
    decision = decision if isinstance(decision, dict) else {}
    approved = decision.get("decision") == "approve"
    review = {
        "reason": reason,
        "decision": "approve" if approved else "reject",
        "note": str(decision.get("note") or "")[:500],
    }
    result: dict[str, Any] = {
        "review_required": True,
        "human_review": review,
        "messages": [{
            "agent": "human_review",
            "action": "approve" if approved else "reject",
            "reason": reason,
        }],
    }
    if not approved:
        result.update({"answer": REJECTED_ANSWER, "final_reason": "review_rejected"})
    return result


def after_human_review(state: HealthcareAgentState) -> str:
    review = state.get("human_review") or {}
    return "rejected" if review.get("decision") == "reject" else "approved"


# ── Interrupt helpers ───────────────────────────────────────────────────────

def extract_interrupt(chunk: Any) -> dict[str, Any] | None:
    """Return the first interrupt payload in a graph output/update, if any."""
    if not isinstance(chunk, dict):
        return None
    interrupts = chunk.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0]
    value = getattr(first, "value", first)
    return dict(value) if isinstance(value, dict) else {"value": value}


# ── Pending-thread registry ─────────────────────────────────────────────────

class PendingReviews:
    """Bounded registry of paused threads; evicts oldest and frees its checkpoint."""

    def __init__(self) -> None:
        self._items: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def add(self, thread_id: str, payload: dict[str, Any], checkpointer: Any) -> None:
        evicted: list[str] = []
        with self._lock:
            self._items[thread_id] = payload
            self._items.move_to_end(thread_id)
            while len(self._items) > _max_pending():
                old, _ = self._items.popitem(last=False)
                evicted.append(old)
        for old in evicted:
            release_thread(checkpointer, old)

    def get(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            payload = self._items.get(thread_id)
            return dict(payload) if payload is not None else None

    def pop(self, thread_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._items.pop(thread_id, None)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


pending_reviews = PendingReviews()


def release_thread(checkpointer: Any, thread_id: str) -> None:
    delete = getattr(checkpointer, "delete_thread", None)
    if callable(delete):
        delete(thread_id)
