"""Offline, deterministic evaluation runner.

Feeds scripted fixture answers through the real LangGraph pipeline (triage,
input and output guardrails) using a stub runtime, so CI can gate guardrail,
routing and scoring logic without a live LLM or datastores. It does not measure
live model quality.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from healthcare_agent.evaluation.agent_eval import (
    evaluate_answer_quality,
    evaluate_evidence_completeness,
    evaluate_routing_accuracy,
)
from healthcare_agent.evaluation.factuality import score_factuality
from healthcare_agent.evaluation.mlflow_eval import score_safety_caveat
from healthcare_agent.orchestration import runtime as runtime_module
from healthcare_agent.orchestration.runtime import AgentRuntime, configure_runtime

DEFAULT_CASES_PATH = Path(__file__).resolve().parents[3] / "tests" / "evals" / "fixtures" / "clinical_eval_cases.json"


def load_cases(path: Path | str | None = None) -> list[dict[str, Any]]:
    cases_path = Path(path or DEFAULT_CASES_PATH)
    if not cases_path.is_file():
        raise FileNotFoundError(
            f"Offline evaluation cases file not found: {cases_path}. "
            "Pass --cases-file with the path to a cases JSON file."
        )
    with open(cases_path, encoding="utf-8") as handle:
        return json.load(handle)["cases"]


def _stub_runtime(case: dict[str, Any], answer: str) -> AgentRuntime:
    terms = list(case.get("required_evidence_terms") or [])
    patient_id = case.get("patient_id") or "P-000"

    def vector_search(query_text: str, pid: str | None, limit: int) -> list[dict[str, Any]]:
        if not terms:
            return []
        return [{"score": 0.9, "event_id": f"evt-{case['id']}", "patient_id": patient_id, "text": ", ".join(terms)}]

    def graph_search(patient_ids: list[str]) -> list[dict[str, Any]]:
        if not terms:
            return []
        return [{"patient_id": patient_id, "conditions": terms}]

    return AgentRuntime(
        vector_search=vector_search,
        graph_search=graph_search,
        synthesize=lambda question, vector_ctx, graph_ctx: answer,
        synthesize_structured=lambda question, vector_ctx, graph_ctx: {"summary": answer},
    )


@contextmanager
def _bound_runtime(runtime: AgentRuntime) -> Iterator[None]:
    previous = runtime_module._runtime
    configure_runtime(runtime)
    try:
        yield
    finally:
        configure_runtime(previous)


def _safety_entry(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    guardrails = result.get("guardrails") or {}
    blocked = bool(guardrails.get("input_blocked") or guardrails.get("output_blocked"))
    expect_block = bool(case.get("must_block"))
    caveat_expected = bool(case.get("must_include_caveat")) and not expect_block
    caveat_ok = score_safety_caveat(result) == 1.0 if caveat_expected else True
    ok = blocked if expect_block else (not blocked and caveat_ok)
    return {
        "metric": "safety",
        "expect_block": expect_block,
        "blocked": blocked,
        "caveat_expected": caveat_expected,
        "caveat_ok": caveat_ok,
        "score": 1.0 if ok else 0.0,
    }


def evaluate_case(case: dict[str, Any], answer_override: str | None = None) -> dict[str, Any]:
    """Run one fixture case through the real graph and score it."""
    from healthcare_agent.orchestration.graph import run_langgraph_query

    answer = answer_override if answer_override is not None else case["stub_answer"]
    with _bound_runtime(_stub_runtime(case, answer)):
        result = run_langgraph_query(case["question"], case.get("patient_id"))

    trace = (result.get("langgraph") or {}).get("agent_trace") or []
    entry: dict[str, Any] = {
        "id": case["id"],
        "category": case.get("category"),
        "answer": result.get("answer", ""),
        "safety": _safety_entry(case, result),
    }
    expected_type = case.get("expected_request_type")
    entry["routing"] = (
        evaluate_routing_accuracy(trace, expected_type) if expected_type else {"metric": "routing_accuracy", "score": 1.0}
    )
    entry["evidence"] = evaluate_evidence_completeness(result)
    entry["answer_quality"] = evaluate_answer_quality(result)
    entry["factuality"] = score_factuality(
        result.get("answer", ""), result.get("vector_context") or [], result.get("graph_context") or []
    )
    return entry


def run_offline_suite(
    cases: list[dict[str, Any]] | None = None, answer_overrides: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    overrides = answer_overrides or {}
    return [evaluate_case(case, overrides.get(case["id"])) for case in (cases if cases is not None else load_cases())]
