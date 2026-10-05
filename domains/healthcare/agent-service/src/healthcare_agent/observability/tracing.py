"""MLflow tracing for the healthcare multi-agent pipeline.

Tracing is optional. Set ``MLFLOW_TRACKING_URI`` to enable it; when unset,
all wrappers call the underlying functions directly.

The implementation deliberately records bounded metadata and counts rather
than unrestricted clinical payloads. Do not add raw patient records, access
tokens, or credentials to span attributes.
"""
from __future__ import annotations

import functools
import os
import time
from typing import Any, Callable

import mlflow
from mlflow.entities import SpanType

_DEFAULT_EXPERIMENT = "healthcare-graphrag"
_MAX_ERROR_LENGTH = 500


def mlflow_enabled() -> bool:
    """Return whether the service should emit MLflow spans."""
    return bool(os.getenv("MLFLOW_TRACKING_URI", "").strip())


def _ensure_experiment() -> str:
    """Select the configured MLflow experiment and return its name."""
    name = os.getenv("MLFLOW_EXPERIMENT_NAME", _DEFAULT_EXPERIMENT)
    mlflow.set_experiment(name)
    return name


def _safe_repr(obj: Any, max_len: int = 2000) -> Any:
    """Return bounded, recursively simplified data for span I/O logging.

    This limits collection sizes and string values, but it is not a
    de-identification mechanism. Callers must avoid passing sensitive values.
    """
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj[:max_len] if isinstance(obj, str) else obj
    if isinstance(obj, dict):
        return {k: _safe_repr(v, max_len) for k, v in list(obj.items())[:20]}
    if isinstance(obj, (list, tuple)):
        return [_safe_repr(v, max_len) for v in obj[:20]]
    text = str(obj)
    return text[:max_len]


def _error_attributes(exc: BaseException, elapsed_ms: float) -> dict[str, Any]:
    return {
        "latency_ms": round(elapsed_ms, 2),
        "outcome": "error",
        "error_type": type(exc).__name__,
        "error": str(exc)[:_MAX_ERROR_LENGTH],
    }


def mlflow_trace(
    span_type: str = SpanType.CHAIN,
    name: str | None = None,
):
    """Decorate a function with an MLflow span.

    Example::

        @mlflow_trace(span_type=SpanType.RETRIEVER, name="vector_search")
        def vector_context(question, patient_id, limit):
            ...
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if not mlflow_enabled():
                return fn(*args, **kwargs)

            with mlflow.start_span(name=name or fn.__name__, span_type=span_type) as span:
                span.set_inputs({"args": _safe_repr(args), "kwargs": _safe_repr(kwargs)})
                started = time.perf_counter()
                try:
                    result = fn(*args, **kwargs)
                except Exception as exc:
                    span.set_attributes(_error_attributes(exc, (time.perf_counter() - started) * 1000))
                    raise
                elapsed_ms = (time.perf_counter() - started) * 1000
                span.set_outputs(_safe_repr(result))
                span.set_attributes({"latency_ms": round(elapsed_ms, 2), "outcome": "success"})
                return result

        return wrapper

    return decorator


def trace_query(
    question: str,
    patient_id: str | None,
    mode: str,
    query_fn: Callable,
    *,
    top_k: int | None = None,
    **extra_kwargs: Any,
) -> dict[str, Any]:
    """Run a query inside a parent span for the complete healthcare pipeline.

    Child spans created by agent, retriever, and LLM wrappers are nested under
    this span when MLflow's active-span context is available.
    """
    kwargs = {key: value for key, value in extra_kwargs.items() if value is not None}
    if not mlflow_enabled():
        return (
            query_fn(question, patient_id, top_k, **kwargs)
            if top_k is not None
            else query_fn(question, patient_id, **kwargs)
        )

    _ensure_experiment()
    with mlflow.start_span(name=f"healthcare_query_{mode}", span_type=SpanType.CHAIN) as root:
        root.set_inputs({"question": question, "patient_id": patient_id, "mode": mode})
        started = time.perf_counter()
        try:
            result = (
                query_fn(question, patient_id, top_k, **kwargs)
                if top_k is not None
                else query_fn(question, patient_id, **kwargs)
            )
        except Exception as exc:
            root.set_attributes(_error_attributes(exc, (time.perf_counter() - started) * 1000))
            raise

        elapsed_ms = (time.perf_counter() - started) * 1000
        root.set_attributes(
            {
                "latency_ms": round(elapsed_ms, 2),
                "outcome": "success",
                "mode": mode,
                "request_type": result.get("request_type", "unknown"),
                "patient_count": len(result.get("patients", [])),
                "vector_hits": len(result.get("vector_context", [])),
                "graph_hits": len(result.get("graph_context", [])),
                "answer_length": len(result.get("answer", "")),
            }
        )
        root.set_outputs(_safe_repr(result))
        return result


def trace_agent_node(agent_name: str, fn: Callable) -> Callable:
    """Wrap a LangGraph node with an ``AGENT`` span."""

    @functools.wraps(fn)
    def wrapper(state):
        if not mlflow_enabled():
            return fn(state)

        with mlflow.start_span(name=f"agent:{agent_name}", span_type=SpanType.AGENT) as span:
            span.set_inputs(
                {
                    "question": state.get("question", ""),
                    "request_type": state.get("request_type", ""),
                    "iteration": state.get("iteration", 0),
                }
            )
            started = time.perf_counter()
            try:
                result = fn(state)
            except Exception as exc:
                span.set_attributes(_error_attributes(exc, (time.perf_counter() - started) * 1000))
                raise

            elapsed_ms = (time.perf_counter() - started) * 1000
            messages = result.get("messages", [])
            attributes = {
                "latency_ms": round(elapsed_ms, 2),
                "outcome": "success",
                "agent": agent_name,
                "message_count": len(messages),
            }
            if messages:
                attributes["action"] = messages[-1].get("action", "")
            span.set_attributes(attributes)
            span.set_outputs(_safe_repr(result))
            return result

    return wrapper


def trace_llm_call(
    fn: Callable,
    *,
    get_model_info: Callable[[], dict[str, Any]] | None = None,
) -> Callable:
    """Wrap LLM generation with an ``LLM`` span and model-routing metadata."""

    @functools.wraps(fn)
    def wrapper(question, vector_ctx, graph_ctx):
        if not mlflow_enabled():
            return fn(question, vector_ctx, graph_ctx)

        with mlflow.start_span(name="llm_generate", span_type=SpanType.LLM) as span:
            span.set_inputs(
                {
                    "question": question,
                    "vector_context_count": len(vector_ctx),
                    "graph_context_count": len(graph_ctx),
                }
            )
            started = time.perf_counter()
            try:
                answer = fn(question, vector_ctx, graph_ctx)
            except Exception as exc:
                span.set_attributes(_error_attributes(exc, (time.perf_counter() - started) * 1000))
                raise

            elapsed_ms = (time.perf_counter() - started) * 1000
            attributes = {
                "latency_ms": round(elapsed_ms, 2),
                "outcome": "success",
                "answer_length": len(answer),
                "is_error": answer.startswith("LLM error:"),
            }
            if get_model_info is not None:
                try:
                    attributes.update(get_model_info())
                except Exception:
                    attributes["model_info_error"] = True
            span.set_attributes(attributes)
            span.set_outputs({"answer": answer[:1000]})
            return answer

    return wrapper


def trace_retriever(name: str, fn: Callable) -> Callable:
    """Wrap vector or graph retrieval with a ``RETRIEVER`` span."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not mlflow_enabled():
            return fn(*args, **kwargs)

        with mlflow.start_span(name=name, span_type=SpanType.RETRIEVER) as span:
            span.set_inputs(_safe_repr({"args": args, "kwargs": kwargs}))
            started = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
            except Exception as exc:
                span.set_attributes(_error_attributes(exc, (time.perf_counter() - started) * 1000))
                raise

            elapsed_ms = (time.perf_counter() - started) * 1000
            result_count = len(result) if isinstance(result, (list, tuple, dict)) else 1
            span.set_attributes(
                {
                    "latency_ms": round(elapsed_ms, 2),
                    "outcome": "success",
                    "result_count": result_count,
                }
            )
            span.set_outputs(_safe_repr(result))
            return result

    return wrapper