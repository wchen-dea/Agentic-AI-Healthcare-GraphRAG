"""MLflow tracing and evaluation for healthcare multi-agent pipelines.

Provides:
- ``@mlflow_trace`` decorator for wrapping agent nodes, retrieval, and LLM calls
- Automatic span creation with healthcare-specific attributes
- Evaluation harness comparing single-pass / ReAct / LangGraph modes
- Custom healthcare scorers: routing, evidence, answer quality, safety

Activation: set ``MLFLOW_TRACKING_URI`` (e.g. ``http://mlflow:5000``)
and optionally ``MLFLOW_EXPERIMENT_NAME``.
"""
from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable

import mlflow
from mlflow.entities import SpanType


# ── Configuration ──────────────────────────────────────────────────────────

_DEFAULT_EXPERIMENT = "healthcare-graphrag"


def mlflow_enabled() -> bool:
    return bool(os.getenv("MLFLOW_TRACKING_URI"))


def _ensure_experiment() -> str:
    name = os.getenv("MLFLOW_EXPERIMENT_NAME", _DEFAULT_EXPERIMENT)
    mlflow.set_experiment(name)
    return name


# ── Tracing decorator ─────────────────────────────────────────────────────

def mlflow_trace(
    span_type: str = SpanType.CHAIN,
    name: str | None = None,
):
    """Decorator that wraps a function in an MLflow trace span.

    Usage::

        @mlflow_trace(span_type=SpanType.RETRIEVER, name="vector_search")
        def vector_context(question, patient_id, limit):
            ...
    """
    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not mlflow_enabled():
                return fn(*args, **kwargs)

            span_name = name or fn.__name__
            with mlflow.start_span(name=span_name, span_type=span_type) as span:
                span.set_inputs({"args": _safe_repr(args), "kwargs": _safe_repr(kwargs)})
                started = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    span.set_outputs(_safe_repr(result))
                    span.set_attributes({
                        "latency_ms": round(elapsed_ms, 2),
                        "outcome": "success",
                    })
                    return result
                except Exception as exc:
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    span.set_attributes({
                        "latency_ms": round(elapsed_ms, 2),
                        "outcome": "error",
                        "error": str(exc)[:500],
                    })
                    raise
        return wrapper
    return decorator


def _safe_repr(obj: Any, max_len: int = 2000) -> Any:
    """Truncate large objects for span I/O logging."""
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    if isinstance(obj, dict):
        return {k: _safe_repr(v, max_len) for k, v in list(obj.items())[:20]}
    if isinstance(obj, (list, tuple)):
        return [_safe_repr(v, max_len) for v in obj[:20]]
    text = str(obj)
    return text[:max_len] if len(text) > max_len else text


# ── Trace lifecycle for full query pipelines ───────────────────────────────

def trace_query(
    question: str,
    patient_id: str | None,
    mode: str,
    query_fn: Callable,
    *,
    top_k: int | None = None,
) -> dict[str, Any]:
    """Execute a query function inside an MLflow trace.

    Creates a parent trace span containing the full pipeline, with
    metadata for the query mode and patient scope.
    """
    if not mlflow_enabled():
        if top_k is not None:
            return query_fn(question, patient_id, top_k)
        return query_fn(question, patient_id)

    _ensure_experiment()

    with mlflow.start_span(name=f"healthcare_query_{mode}", span_type=SpanType.CHAIN) as root:
        root.set_inputs({
            "question": question,
            "patient_id": patient_id,
            "mode": mode,
        })
        started = time.perf_counter()

        if top_k is not None:
            result = query_fn(question, patient_id, top_k)
        else:
            result = query_fn(question, patient_id)

        elapsed_ms = (time.perf_counter() - started) * 1000
        root.set_attributes({
            "latency_ms": round(elapsed_ms, 2),
            "mode": mode,
            "request_type": result.get("request_type", "unknown"),
            "patient_count": len(result.get("patients", [])),
            "vector_hits": len(result.get("vector_context", [])),
            "graph_hits": len(result.get("graph_context", [])),
            "answer_length": len(result.get("answer", "")),
        })
        root.set_outputs(_safe_repr(result))

    return result


# ── Agent node tracing ────────────────────────────────────────────────────

def trace_agent_node(agent_name: str, fn: Callable) -> Callable:
    """Wrap a LangGraph agent node function with an MLflow span."""
    @functools.wraps(fn)
    def wrapper(state):
        if not mlflow_enabled():
            return fn(state)

        with mlflow.start_span(
            name=f"agent:{agent_name}",
            span_type=SpanType.AGENT,
        ) as span:
            span.set_inputs({
                "question": state.get("question", ""),
                "request_type": state.get("request_type", ""),
                "iteration": state.get("iteration", 0),
            })
            started = time.perf_counter()
            result = fn(state)
            elapsed_ms = (time.perf_counter() - started) * 1000

            attrs = {"latency_ms": round(elapsed_ms, 2), "agent": agent_name}
            messages = result.get("messages", [])
            if messages:
                attrs["action"] = messages[-1].get("action", "")
            span.set_attributes(attrs)
            span.set_outputs(_safe_repr(result))
            return result

    return wrapper


# ── LLM call tracing ─────────────────────────────────────────────────────

def trace_llm_call(fn: Callable) -> Callable:
    """Wrap the LLM synthesis function with an MLflow LLM span."""
    @functools.wraps(fn)
    def wrapper(question, vector_ctx, graph_ctx):
        if not mlflow_enabled():
            return fn(question, vector_ctx, graph_ctx)

        with mlflow.start_span(name="llm_generate", span_type=SpanType.LLM) as span:
            span.set_inputs({
                "question": question,
                "vector_context_count": len(vector_ctx),
                "graph_context_count": len(graph_ctx),
            })
            started = time.perf_counter()
            answer = fn(question, vector_ctx, graph_ctx)
            elapsed_ms = (time.perf_counter() - started) * 1000
            span.set_attributes({
                "latency_ms": round(elapsed_ms, 2),
                "answer_length": len(answer),
                "is_error": answer.startswith("LLM error:"),
            })
            span.set_outputs({"answer": answer[:1000]})
            return answer

    return wrapper


# ── Retriever tracing ────────────────────────────────────────────────────

def trace_retriever(name: str, fn: Callable) -> Callable:
    """Wrap a retrieval function with an MLflow RETRIEVER span."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not mlflow_enabled():
            return fn(*args, **kwargs)

        with mlflow.start_span(name=name, span_type=SpanType.RETRIEVER) as span:
            span.set_inputs(_safe_repr({"args": args, "kwargs": kwargs}))
            started = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed_ms = (time.perf_counter() - started) * 1000
            span.set_attributes({
                "latency_ms": round(elapsed_ms, 2),
                "result_count": len(result) if isinstance(result, list) else 1,
            })
            span.set_outputs(_safe_repr(result))
            return result

    return wrapper
