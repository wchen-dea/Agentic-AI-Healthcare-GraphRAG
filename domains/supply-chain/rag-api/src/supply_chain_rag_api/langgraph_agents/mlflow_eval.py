"""MLflow evaluation harness for healthcare agent pipelines.

Runs the standard evaluation dataset through each query mode and logs
results as MLflow metrics, parameters, and a comparison artifact.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Callable

import mlflow

from .evaluation import (
    EVALUATION_DATASET,
    evaluate_agent_coverage,
    evaluate_answer_quality,
    evaluate_evidence_completeness,
    evaluate_routing_accuracy,
)
from .mlflow_tracing import _ensure_experiment, mlflow_enabled


# ── Thin wrappers that return float scores (evaluation.py returns dicts) ──

def score_routing(trace_messages: list[dict[str, Any]], expected_type: str) -> float:
    return evaluate_routing_accuracy(trace_messages, expected_type)["score"]


def score_agent_coverage(
    trace_messages: list[dict[str, Any]], expected_agents: list[str],
) -> float:
    return evaluate_agent_coverage(trace_messages, expected_agents)["score"]


def score_evidence_completeness(result: dict[str, Any]) -> float:
    return evaluate_evidence_completeness(result)["score"]


def score_answer_quality(result: dict[str, Any]) -> float:
    return evaluate_answer_quality(result)["score"]


def score_safety_caveat(result: dict[str, Any]) -> float:
    """Check that the answer includes a safety/clinical disclaimer."""
    answer = (result.get("answer") or "").lower()
    safety_phrases = [
        "not medical advice",
        "consult",
        "clinical judgment",
        "demo data",
        "synthetic",
        "safety caveat",
        "not a substitute",
        "healthcare professional",
    ]
    return 1.0 if any(p in answer for p in safety_phrases) else 0.0


def score_latency(elapsed_seconds: float, threshold: float = 30.0) -> float:
    """1.0 when under threshold, linearly decreasing to 0.0 at 2x threshold."""
    if elapsed_seconds <= threshold:
        return 1.0
    if elapsed_seconds >= threshold * 2:
        return 0.0
    return 1.0 - (elapsed_seconds - threshold) / threshold


# ── Evaluation runner ─────────────────────────────────────────────────────

def run_mlflow_evaluation(
    query_fn: Callable,
    mode: str,
    *,
    dataset: list[dict[str, Any]] | None = None,
    log_to_mlflow: bool = True,
) -> list[dict[str, Any]]:
    """Run the evaluation dataset and optionally log to MLflow.

    Each case is scored on six dimensions; per-case and aggregate metrics
    are logged as an MLflow run.
    """
    cases = dataset or EVALUATION_DATASET
    if log_to_mlflow and mlflow_enabled():
        _ensure_experiment()

    results: list[dict[str, Any]] = []

    with mlflow.start_run(run_name=f"eval_{mode}") if (log_to_mlflow and mlflow_enabled()) else _noop_context():
        if log_to_mlflow and mlflow_enabled():
            mlflow.log_param("mode", mode)
            mlflow.log_param("dataset_size", len(cases))

        totals = {
            "routing": 0.0,
            "agent_coverage": 0.0,
            "evidence": 0.0,
            "answer_quality": 0.0,
            "safety_caveat": 0.0,
            "latency": 0.0,
        }

        for i, case in enumerate(cases):
            started = time.perf_counter()
            try:
                result = query_fn(case["question"], case.get("patient_id"))
            except Exception as exc:
                result = {"answer": f"LLM error: {exc}", "vector_context": [], "graph_context": []}
            elapsed = time.perf_counter() - started

            trace = _extract_trace(result)

            scores = {
                "routing": score_routing(trace, case["expected_type"]),
                "agent_coverage": score_agent_coverage(trace, case.get("expected_agents", [])),
                "evidence": score_evidence_completeness(result),
                "answer_quality": score_answer_quality(result),
                "safety_caveat": score_safety_caveat(result),
                "latency": score_latency(elapsed),
            }

            case_result = {
                "case_index": i,
                "question": case["question"][:80],
                "expected_type": case["expected_type"],
                "actual_type": result.get("request_type"),
                "mode": mode,
                "elapsed_seconds": round(elapsed, 3),
                "scores": scores,
            }
            results.append(case_result)

            for k, v in scores.items():
                totals[k] += v

            if log_to_mlflow and mlflow_enabled():
                for k, v in scores.items():
                    mlflow.log_metric(f"case_{i}_{k}", v, step=i)
                mlflow.log_metric(f"case_{i}_latency_seconds", round(elapsed, 3), step=i)

        n = max(len(cases), 1)
        aggregates = {k: round(v / n, 4) for k, v in totals.items()}

        if log_to_mlflow and mlflow_enabled():
            for k, v in aggregates.items():
                mlflow.log_metric(f"avg_{k}", v)
            mlflow.log_text(
                json.dumps(results, indent=2, default=str),
                "evaluation_results.json",
            )

        results.append({"aggregate": aggregates, "mode": mode})

    return results


def compare_modes(
    query_fns: dict[str, Callable],
    *,
    dataset: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run evaluation across multiple modes and return a comparison summary.

    ``query_fns`` maps mode names to callables: e.g.
    ``{"single_pass": run_query, "langgraph": run_langgraph_query}``
    """
    comparison: dict[str, Any] = {}
    for mode, fn in query_fns.items():
        results = run_mlflow_evaluation(fn, mode, dataset=dataset)
        agg = next((r for r in results if "aggregate" in r), {})
        comparison[mode] = agg.get("aggregate", {})

    if mlflow_enabled():
        _ensure_experiment()
        with mlflow.start_run(run_name="mode_comparison"):
            for mode, scores in comparison.items():
                for metric, value in scores.items():
                    mlflow.log_metric(f"{mode}_{metric}", value)
            mlflow.log_text(
                json.dumps(comparison, indent=2, default=str),
                "mode_comparison.json",
            )

    return comparison


# ── Helpers ───────────────────────────────────────────────────────────────

def _extract_trace(result: dict[str, Any]) -> list[dict[str, Any]]:
    if "langgraph" in result:
        return result["langgraph"].get("agent_trace", [])
    if "react" in result:
        return result["react"].get("actions", [])
    return []


class _noop_context:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
