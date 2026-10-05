from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from healthcare_agent.orchestration.planner import classify_request_type

FIXTURE = Path(__file__).parent / "fixtures" / "planner_route_fixtures.json"


def test_golden_questions_route_without_an_llm() -> None:
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert len(cases) >= 10
    for case in cases:
        actual = classify_request_type(case["question"], case["patient_id"])
        assert actual == case["expected_request_type"], case["id"]


@pytest.mark.skipif(
    os.getenv("RUN_LIVE_LLM_EVAL") != "1",
    reason="live LLM evaluation is opt-in; CI uses deterministic golden tests",
)
def test_live_llm_golden_questions() -> None:
    from healthcare_agent.evaluation.agent_eval import run_evaluation_suite
    from healthcare_agent.main import queries

    results = run_evaluation_suite(queries.run_query, mode="single_pass")
    assert results
    assert all(result.get("answer_quality", {}).get("has_answer") for result in results)