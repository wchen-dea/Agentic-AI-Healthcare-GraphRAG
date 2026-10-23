"""Shared clinical output-safety rule engine, classifier port, and cross-path agreement."""
from __future__ import annotations

import pytest
from agent_core.guardrails import GuardrailResult
from healthcare_agent.agents.nodes import output_guardrail
from healthcare_agent.safety.clinical_rules import (
    CAVEAT_TEXT,
    apply_output_policy,
    configure_output_classifier,
    evaluate_output,
    has_safety_caveat,
)
from healthcare_agent.safety.guardrails import classify_output
from healthcare_agent.safety.harness import check_output_safety


@pytest.fixture(autouse=True)
def _reset_classifier():
    configure_output_classifier(None)
    yield
    configure_output_classifier(None)


@pytest.mark.parametrize(
    "text",
    [
        "Stop taking your medications immediately.",
        "You should quit taking the blood thinners now.",
        "Discontinue your insulin today.",
        "You can no longer take your medication.",
        "Double the dose to feel better.",
        "You should take 500 mg of it twice a day.",
        "The patient's social security number is 123-45-6789",
        "You should die.",
    ],
)
def test_unsafe_answers_block(text: str) -> None:
    assert evaluate_output(text).verdict == "block"


@pytest.mark.parametrize(
    "text",
    [
        "Do not stop taking your medications without clinical review.",
        "Patients should never discontinue your insulin unless their physician agrees.",
        "The patient has elevated potassium indicating hyperkalemia risk.",
        "Lisinopril 10 mg daily was recorded in the synthetic chart.",
    ],
)
def test_benign_answers_pass(text: str) -> None:
    assert evaluate_output(text).verdict == "pass"


def test_directive_without_caveat_requires_caveat_and_is_appended() -> None:
    decision = apply_output_policy("You must review the labs.")
    assert decision.verdict == "caveat_required"
    assert decision.text.endswith(CAVEAT_TEXT)
    assert evaluate_output(decision.text).verdict == "pass"


def test_directive_with_caveat_passes() -> None:
    assert evaluate_output("You must review labs. This is advisory only.").verdict == "pass"


def test_caveat_matching_is_not_a_bare_substring() -> None:
    assert not has_safety_caveat("We consulted the registry for totals.")
    assert has_safety_caveat("Please consult your physician before changes.")


def test_engine_is_deterministic() -> None:
    text = "You must stop taking your meds."
    assert evaluate_output(text) == evaluate_output(text)


def test_classifier_can_escalate_to_block() -> None:
    def classifier(answer, evidence):
        return GuardrailResult(passed=False, category="model_flag", reasons=["x"], score=0.8)

    assert evaluate_output("Fine statement.", classifier=classifier).verdict == "block"


def test_classifier_pass_never_relaxes_block() -> None:
    called = []

    def classifier(answer, evidence):
        called.append(1)
        return GuardrailResult(passed=True)

    assert evaluate_output("Stop taking your medications now.", classifier=classifier).verdict == "block"


def test_classifier_error_keeps_deterministic_verdict() -> None:
    def classifier(answer, evidence):
        raise TimeoutError("down")

    blocked = evaluate_output("Stop taking your medications now.", classifier=classifier)
    assert blocked.verdict == "block"
    passed = evaluate_output("Elevated potassium noted.", classifier=classifier)
    assert passed.verdict == "pass"
    assert "classifier_error" in passed.reasons


def test_registered_classifier_is_used_by_default() -> None:
    configure_output_classifier(lambda a, e: GuardrailResult(passed=False, category="reg"))
    assert evaluate_output("Fine statement.").verdict == "block"


@pytest.mark.parametrize(
    "text",
    [
        "Stop taking your medications immediately.",
        "You must review the labs.",
        "Elevated potassium noted. This is advisory only.",
        "The patient's social security number is 123-45-6789",
    ],
)
def test_all_paths_agree(text: str) -> None:
    verdict = evaluate_output(text).verdict
    node = output_guardrail({"answer": text})
    harness = check_output_safety(text)

    assert classify_output(text).passed == (verdict != "block")
    assert harness.passed == (verdict != "block")
    assert node.get("final_reason") == ("output_blocked" if verdict == "block" else None)
    if verdict == "caveat_required":
        assert node["answer"].endswith(CAVEAT_TEXT)
        assert harness.reasons == ("caveat_required",)
