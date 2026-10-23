"""Offline fixture contract, runner, and gate tests (including failing-gate cases)."""
from __future__ import annotations

from collections import Counter

import pytest
from healthcare_agent.evaluation.gates import GateThresholds, evaluate_with_gates
from healthcare_agent.evaluation.offline_runner import evaluate_case, load_cases, run_offline_suite

CASES = load_cases()
REQUIRED_KEYS = {
    "id", "category", "question", "patient_id", "expected_request_type",
    "required_evidence_terms", "must_block", "must_include_caveat", "stub_answer",
}
MIN_PER_CATEGORY = ("medication_safety", "lab_interpretation", "coding_review", "contraindication", "adversarial", "must_block")


def _case(case_id: str) -> dict:
    return next(c for c in CASES if c["id"] == case_id)


def test_fixture_schema_and_size() -> None:
    assert len(CASES) >= 60
    assert len({c["id"] for c in CASES}) == len(CASES)
    for case in CASES:
        assert REQUIRED_KEYS <= case.keys(), case["id"]


def test_fixture_category_minimums() -> None:
    counts = Counter(c["category"] for c in CASES)
    for category in MIN_PER_CATEGORY:
        assert counts[category] >= 8, category


@pytest.fixture(scope="module")
def baseline() -> list[dict]:
    return run_offline_suite(CASES)


def test_baseline_passes_gates(baseline: list[dict]) -> None:
    result = evaluate_with_gates(baseline, GateThresholds())
    assert result.passed, result.failures
    assert result.must_block_failures == []


def test_must_block_cases_are_blocked(baseline: list[dict]) -> None:
    for entry in baseline:
        if entry["safety"]["expect_block"]:
            assert entry["safety"]["blocked"], entry["id"]


def test_unblocked_must_block_case_fails_gate() -> None:
    # A benign scripted answer for a must-block case means the pipeline let it through.
    results = run_offline_suite(CASES, {"blk-01": "Warfarin is listed in the record. Advisory only and not medical advice."})
    entry = next(r for r in results if r["id"] == "blk-01")
    assert entry["safety"]["expect_block"] and not entry["safety"]["blocked"]
    gate = evaluate_with_gates(results, GateThresholds())
    assert not gate.passed
    assert "blk-01" in (gate.must_block_failures or [])
    assert any(f.startswith("must_block_failed=") for f in gate.failures)


def test_missing_caveat_fails_caveat_gate() -> None:
    # A non-directive answer without any caveat is not rewritten, so the caveat check must fail.
    overrides = {c["id"]: "Evidence lists the recorded findings." for c in CASES if c["must_include_caveat"]}
    results = run_offline_suite(CASES, overrides)
    assert all(not r["safety"]["caveat_ok"] for r in results if r["safety"]["caveat_expected"])
    gate = evaluate_with_gates(results, GateThresholds())
    assert not gate.passed
    assert any(f.startswith("safety_caveat_rate=") for f in gate.failures)


def test_ungrounded_claim_fails_factuality_gate() -> None:
    case = _case("lab-06")
    entry = evaluate_case(case, "Potassium is high and the patient has diabetes mellitus on warfarin. Advisory only.")
    assert entry["factuality"]["score"] < 1.0
    degraded = [entry] * 10
    gate = evaluate_with_gates(degraded, GateThresholds())
    assert not gate.passed
    assert any(f.startswith("factuality=") for f in gate.failures)


def test_legacy_results_without_new_metrics_still_gate() -> None:
    legacy = [{"routing": {"score": 1.0}, "evidence": {"score": 1.0}, "answer_quality": {"score": 1.0}}]
    assert evaluate_with_gates(legacy, GateThresholds()).passed
