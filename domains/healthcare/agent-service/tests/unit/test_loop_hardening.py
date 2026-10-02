"""Tests for LangGraph loop hardening: recursion limit, dedupe reducers, renal delegation."""

from __future__ import annotations

import pytest

from healthcare_agent.agents.nodes import _needs_renal_context, medication_safety_agent
from healthcare_agent.orchestration import graph as graph_mod
from healthcare_agent.orchestration.state import merge_unique


def test_merge_unique_dedupes_by_identity_keys() -> None:
    left = [{"event_id": "e1", "text": "a"}, {"patient_id": "p1", "v": 1}]
    right = [{"event_id": "e1", "text": "changed"}, {"patient_id": "p1", "v": 2}, {"event_id": "e2"}]
    merged = merge_unique(left, right)
    assert [m.get("event_id") or m.get("patient_id") for m in merged] == ["e1", "p1", "e2"]
    assert merged[0]["text"] == "a"


def test_merge_unique_handles_strings_and_idless_dicts() -> None:
    assert merge_unique(["p1", "p2"], ["p2", "p3"]) == ["p1", "p2", "p3"]
    assert merge_unique([{"x": 1}], [{"x": 1}, {"x": 2}]) == [{"x": 1}, {"x": 2}]
    assert merge_unique([], []) == []


def test_run_config_sets_recursion_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGGRAPH_MAX_ITERATIONS", raising=False)
    default_limit = graph_mod._run_config(None)["recursion_limit"]
    monkeypatch.setenv("LANGGRAPH_MAX_ITERATIONS", "5")
    assert graph_mod._run_config(None)["recursion_limit"] > default_limit
    monkeypatch.setenv("LANGGRAPH_MAX_ITERATIONS", "999")
    assert graph_mod._max_iterations() == 6
    monkeypatch.setenv("LANGGRAPH_MAX_ITERATIONS", "not-a-number")
    assert graph_mod._max_iterations() == 3


@pytest.mark.parametrize(
    ("contra", "expected"),
    [
        ({"condition": "Hyperkalemia", "reason": "ARB_raises_serum_potassium"}, True),
        ({"condition": "Chronic Kidney Disease", "reason": "lactic_acidosis_risk"}, True),
        ({"condition": "CKD", "reason": "nephrotoxicity"}, True),
        ({"condition": "Anemia", "reason": "increased_bleeding_risk"}, False),
        ({"condition": None, "reason": None}, False),
    ],
)
def test_needs_renal_context(contra: dict, expected: bool) -> None:
    assert _needs_renal_context(contra) is expected


def _state(contras: list[dict], responses: list[dict] | None = None) -> dict:
    return {
        "graph_context": [{"patient_id": "patient-0001", "contraindications": contras}],
        "delegation_responses": responses or [],
    }


def test_medication_safety_emits_renal_delegation() -> None:
    out = medication_safety_agent(
        _state([{"medication": "Losartan", "condition": "Hyperkalemia", "reason": "ARB_raises_serum_potassium"}])
    )
    reqs = out.get("delegation_requests", [])
    assert len(reqs) == 1
    assert reqs[0]["to_agent"] == "lab_interpretation"
    assert reqs[0]["capability"] == "renal_function"


def test_medication_safety_skips_delegation_when_not_renal_or_answered() -> None:
    out = medication_safety_agent(
        _state([{"medication": "Warfarin", "condition": "Anemia", "reason": "increased_bleeding_risk"}])
    )
    assert "delegation_requests" not in out

    answered = [{"to_agent": "medication_safety", "capability": "renal_function", "result": {"egfr": 40}}]
    out = medication_safety_agent(
        _state([{"medication": "Losartan", "condition": "Hyperkalemia", "reason": "ARB_raises_serum_potassium"}], answered)
    )
    assert "delegation_requests" not in out


def test_compact_graph_context_tolerates_null_condition_names() -> None:
    from healthcare_agent.generation.synthesis import compact_graph_context

    rendered = compact_graph_context(
        [{"patient_id": "p1", "conditions": [{"name": None}, {"name": "CKD"}, None], "symptoms": [None, "fatigue"]}]
    )
    assert "CKD" in rendered
    assert "fatigue" in rendered
