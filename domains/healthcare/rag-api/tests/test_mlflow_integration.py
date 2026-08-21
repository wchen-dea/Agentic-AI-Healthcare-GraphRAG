"""Tests for MLflow tracing and evaluation integration."""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from langgraph_agents.mlflow_tracing import (
    _safe_repr,
    mlflow_enabled,
    mlflow_trace,
    trace_agent_node,
    trace_llm_call,
    trace_query,
    trace_retriever,
)
from langgraph_agents.mlflow_eval import (
    _extract_trace,
    compare_modes,
    run_mlflow_evaluation,
    score_answer_quality,
    score_agent_coverage,
    score_evidence_completeness,
    score_latency,
    score_routing,
    score_safety_caveat,
)


# ── mlflow_enabled ─────────────────────────────────────────────────────────

class TestMlflowEnabled:
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)
            assert mlflow_enabled() is False

    def test_enabled_when_uri_set(self):
        with patch.dict(os.environ, {"MLFLOW_TRACKING_URI": "http://mlflow:5000"}):
            assert mlflow_enabled() is True


# ── _safe_repr ─────────────────────────────────────────────────────────────

class TestSafeRepr:
    def test_scalars_pass_through(self):
        assert _safe_repr("hello") == "hello"
        assert _safe_repr(42) == 42
        assert _safe_repr(None) is None

    def test_dict_truncated(self):
        big = {f"k{i}": i for i in range(50)}
        result = _safe_repr(big)
        assert len(result) == 20

    def test_list_truncated(self):
        big = list(range(50))
        result = _safe_repr(big)
        assert len(result) == 20


# ── mlflow_trace decorator ────────────────────────────────────────────────

class TestMlflowTrace:
    def test_passthrough_when_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            @mlflow_trace(name="test_fn")
            def my_fn(x):
                return x * 2

            assert my_fn(5) == 10

    @patch("langgraph_agents.mlflow_tracing.mlflow_enabled", return_value=True)
    @patch("langgraph_agents.mlflow_tracing.mlflow")
    def test_creates_span_when_enabled(self, mock_mlflow, mock_enabled):
        mock_span = MagicMock()
        mock_mlflow.start_span.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_mlflow.start_span.return_value.__exit__ = MagicMock(return_value=False)

        @mlflow_trace(name="traced_fn")
        def my_fn(x):
            return x + 1

        result = my_fn(3)
        assert result == 4
        mock_mlflow.start_span.assert_called_once()


# ── trace_agent_node ──────────────────────────────────────────────────────

class TestTraceAgentNode:
    def test_passthrough_when_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def my_agent(state):
                return {"messages": [{"agent": "test"}]}

            wrapped = trace_agent_node("test", my_agent)
            result = wrapped({"question": "hi"})
            assert result["messages"][0]["agent"] == "test"


# ── trace_llm_call ───────────────────────────────────────────────────────

class TestTraceLlmCall:
    def test_passthrough_when_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def my_llm(q, v, g):
                return "answer"

            wrapped = trace_llm_call(my_llm)
            assert wrapped("q", [], []) == "answer"


# ── trace_retriever ──────────────────────────────────────────────────────

class TestTraceRetriever:
    def test_passthrough_when_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def my_retriever(q, pid, k):
                return [{"event_id": "e1"}]

            wrapped = trace_retriever("vector", my_retriever)
            result = wrapped("q", None, 5)
            assert len(result) == 1


# ── trace_query ──────────────────────────────────────────────────────────

class TestTraceQuery:
    def test_passthrough_when_disabled(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def my_query(q, pid):
                return {"answer": "ok"}

            result = trace_query("q", None, "test", my_query)
            assert result["answer"] == "ok"

    def test_passes_top_k(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def my_query(q, pid, top_k):
                return {"answer": "ok", "top_k": top_k}

            result = trace_query("q", None, "test", my_query, top_k=10)
            assert result["top_k"] == 10


# ── Evaluation scorers ───────────────────────────────────────────────────

class TestScorers:
    def test_routing_correct(self):
        trace = [{"agent": "triage", "request_type": "medication_safety"}]
        assert score_routing(trace, "medication_safety") == 1.0

    def test_routing_wrong(self):
        trace = [{"agent": "triage", "request_type": "patient_summary"}]
        assert score_routing(trace, "medication_safety") == 0.0

    def test_routing_no_triage(self):
        assert score_routing([], "medication_safety") == 0.0

    def test_agent_coverage_full(self):
        trace = [{"agent": "a"}, {"agent": "b"}]
        assert score_agent_coverage(trace, ["a", "b"]) == 1.0

    def test_agent_coverage_partial(self):
        trace = [{"agent": "a"}]
        assert abs(score_agent_coverage(trace, ["a", "b"]) - 0.5) < 0.01

    def test_evidence_both(self):
        assert score_evidence_completeness({"vector_context": [1], "graph_context": [2]}) == 1.0

    def test_evidence_none(self):
        assert score_evidence_completeness({"vector_context": [], "graph_context": []}) == 0.0

    def test_answer_quality_good(self):
        assert score_answer_quality({"answer": "x" * 100}) == 1.0

    def test_answer_quality_error(self):
        assert score_answer_quality({"answer": "LLM error: timeout"}) == 0.0

    def test_answer_quality_short(self):
        assert score_answer_quality({"answer": "ok"}) == 0.5

    def test_safety_caveat_present(self):
        assert score_safety_caveat({"answer": "This is not medical advice."}) == 1.0

    def test_safety_caveat_missing(self):
        assert score_safety_caveat({"answer": "Patient has hypertension."}) == 0.0

    def test_latency_fast(self):
        assert score_latency(5.0) == 1.0

    def test_latency_slow(self):
        assert score_latency(60.0) == 0.0

    def test_latency_mid(self):
        assert 0.0 < score_latency(40.0) < 1.0


# ── _extract_trace ───────────────────────────────────────────────────────

class TestExtractTrace:
    def test_langgraph_trace(self):
        result = {"langgraph": {"agent_trace": [{"agent": "triage"}]}}
        assert len(_extract_trace(result)) == 1

    def test_react_trace(self):
        result = {"react": {"actions": [{"action": "retrieve"}]}}
        assert len(_extract_trace(result)) == 1

    def test_no_trace(self):
        assert _extract_trace({"answer": "ok"}) == []


# ── run_mlflow_evaluation (offline mode) ─────────────────────────────────

class TestRunMlflowEvaluation:
    def test_runs_without_mlflow(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def mock_query(question, patient_id):
                return {
                    "request_type": "patient_summary",
                    "vector_context": [{"event_id": "e1"}],
                    "graph_context": [{"patient_id": "P-001"}],
                    "answer": "The patient has conditions. This is not medical advice. " * 3,
                    "patients": ["P-001"],
                }

            results = run_mlflow_evaluation(mock_query, "test", log_to_mlflow=False)
            # 5 cases + 1 aggregate
            assert len(results) == 6
            agg = results[-1]
            assert "aggregate" in agg
            assert agg["mode"] == "test"


# ── compare_modes (offline mode) ─────────────────────────────────────────

class TestCompareModes:
    def test_compares_two_modes(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("MLFLOW_TRACKING_URI", None)

            def mock_a(q, pid):
                return {
                    "request_type": "patient_summary",
                    "vector_context": [{"x": 1}],
                    "graph_context": [{"y": 2}],
                    "answer": "Good answer with safety caveat: not medical advice. " * 2,
                }

            def mock_b(q, pid):
                return {
                    "request_type": "patient_summary",
                    "vector_context": [],
                    "graph_context": [],
                    "answer": "LLM error: timeout",
                }

            comparison = compare_modes({"mode_a": mock_a, "mode_b": mock_b})
            assert "mode_a" in comparison
            assert "mode_b" in comparison
            assert comparison["mode_a"]["evidence"] > comparison["mode_b"]["evidence"]
