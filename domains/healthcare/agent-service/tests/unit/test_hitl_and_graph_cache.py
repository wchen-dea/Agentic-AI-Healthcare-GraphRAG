"""Tests for compiled-graph caching and human-in-the-loop review."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from healthcare_agent.orchestration import graph as graph_module
from healthcare_agent.orchestration import runtime as runtime_module
from healthcare_agent.orchestration.hitl import (
    REJECTED_ANSWER,
    extract_interrupt,
    get_checkpointer,
    pending_reviews,
    review_reason,
)
from healthcare_agent.orchestration.memory import get_session_store
from healthcare_agent.orchestration.orchestrator import LangGraphOrchestrator
from healthcare_agent.orchestration.query_service import QueryService
from healthcare_agent.orchestration.runtime import AgentRuntime, configure_runtime


def _runtime() -> AgentRuntime:
    return AgentRuntime(
        vector_search=lambda q, pid, limit: [
            {"score": 0.9, "event_id": "evt-1", "patient_id": "P-001", "event_type": "lab_result", "text": "eGFR 42"}
        ],
        graph_search=lambda pids: [{"patient_id": pid, "conditions": ["CKD"]} for pid in pids],
        synthesize=lambda q, v, g: "Advisory: clinical review recommended.",
        synthesize_structured=lambda q, v, g: {"summary": "Structured.", "risk_level": "moderate"},
    )


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch):
    previous = runtime_module._runtime
    configure_runtime(_runtime())
    monkeypatch.delenv("HITL_ENABLED", raising=False)
    graph_module.clear_graph_cache()
    get_checkpointer.cache_clear()
    pending_reviews.clear()
    yield
    graph_module.clear_graph_cache()
    get_checkpointer.cache_clear()
    pending_reviews.clear()
    configure_runtime(previous)


@pytest.fixture
def hitl_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HITL_ENABLED", "1")
    graph_module.clear_graph_cache()


@pytest.fixture
def medication_request():
    with patch(
        "healthcare_agent.orchestration.planner.classify_request_type",
        return_value="medication_safety",
    ):
        yield


# ── Graph cache ─────────────────────────────────────────────────────────────

def test_compiled_graph_is_cached_and_clearable() -> None:
    first = graph_module.get_compiled_graph()
    assert graph_module.get_compiled_graph() is first
    graph_module.clear_graph_cache()
    assert graph_module.get_compiled_graph() is not first


def test_cache_is_keyed_by_hitl_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    plain = graph_module.get_compiled_graph()
    monkeypatch.setenv("HITL_ENABLED", "true")
    with_hitl = graph_module.get_compiled_graph()
    assert with_hitl is not plain
    assert getattr(with_hitl, "checkpointer", None) is get_checkpointer()


# ── HITL disabled ───────────────────────────────────────────────────────────

def test_hitl_disabled_completes_with_thread_id(medication_request) -> None:
    result = LangGraphOrchestrator.build().run("Check medication interactions", "P-001")
    assert result["status"] == "completed"
    assert result["thread_id"]
    assert result["answer"].startswith("Advisory")


# ── HITL enabled ────────────────────────────────────────────────────────────

def test_medication_request_pauses_then_approve_completes(hitl_on, medication_request) -> None:
    orchestrator = LangGraphOrchestrator.build()
    paused = orchestrator.run("Check medication interactions", "P-001")

    assert paused["status"] == "pending_approval"
    assert paused["langgraph"]["final_reason"] == "pending_review"
    thread_id = paused["thread_id"]
    assert paused["human_review"]["reason"] == "medication_safety"
    assert orchestrator.pending(thread_id)["patient_id"] == "P-001"

    resumed = orchestrator.resume(thread_id, "approve", "ok")
    assert resumed["status"] == "completed"
    assert resumed["answer"].startswith("Advisory")
    assert resumed["human_review"]["decision"] == "approve"
    assert orchestrator.pending(thread_id) is None
    with pytest.raises(KeyError):
        orchestrator.resume(thread_id, "approve")


def test_reject_returns_declined_answer(hitl_on, medication_request) -> None:
    orchestrator = LangGraphOrchestrator.build()
    paused = orchestrator.run("Check medication interactions", "P-001")

    rejected = orchestrator.resume(paused["thread_id"], "reject", "unsafe")
    assert rejected["answer"] == REJECTED_ANSWER
    assert rejected["langgraph"]["final_reason"] == "review_rejected"
    assert rejected["human_review"]["decision"] == "reject"


def test_stream_emits_pending_result(hitl_on, medication_request) -> None:
    events = list(LangGraphOrchestrator.build().stream("Check medication interactions", "P-001"))
    kind, result = events[-1]
    assert kind == "result"
    assert result["status"] == "pending_approval"
    assert pending_reviews.get(result["thread_id"]) is not None


def test_unknown_thread_raises_key_error(hitl_on) -> None:
    with pytest.raises(KeyError):
        LangGraphOrchestrator.build().resume("missing", "approve")


# ── Memory stays in sync with HITL ──────────────────────────────────────────

def test_pending_turn_is_not_remembered_until_resumed(hitl_on, medication_request) -> None:
    session_id = "hitl-session-test"
    store = get_session_store()
    store.delete(session_id)
    service = QueryService(max_context_items=8)

    paused = service.run_query("Check medication interactions", "P-001", session_id=session_id)
    assert paused["status"] == "pending_approval"
    session = store.get(session_id)
    assert session is None or len(session.turns) == 0

    service.resume(paused["thread_id"], "approve", session_id=session_id)
    session = store.get(session_id)
    assert session is not None
    assert [turn.question for turn in session.turns] == ["Check medication interactions"]
    store.delete(session_id)


def test_service_resume_unknown_thread_raises() -> None:
    with pytest.raises(KeyError):
        QueryService(max_context_items=8).resume("missing", "approve")


# ── Helpers ─────────────────────────────────────────────────────────────────

def test_review_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HITL_CONFIDENCE_THRESHOLD", "0.5")
    assert review_reason({"request_type": "medication_safety", "confidence": 0.99}) == "medication_safety"
    assert review_reason({"request_type": "patient_summary", "confidence": 0.1}) == "low_confidence"
    assert review_reason({"request_type": "patient_summary", "confidence": 0.9}) is None


def test_extract_interrupt() -> None:
    class _Interrupt:
        value: Any = {"reason": "low_confidence"}

    assert extract_interrupt({"__interrupt__": [_Interrupt()]}) == {"reason": "low_confidence"}
    assert extract_interrupt({"answer": "x"}) is None
    assert extract_interrupt(None) is None
