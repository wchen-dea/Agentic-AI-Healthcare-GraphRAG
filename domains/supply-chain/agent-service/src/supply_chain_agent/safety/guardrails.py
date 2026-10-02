"""Deterministic input/output guardrails for the supply-chain agent.

Composes the domain-neutral checks in ``agent_core.guardrails`` with
supply-chain sensitive-data rules from ``safety.harness``.
"""
from __future__ import annotations

from agent_core.guardrails import GuardrailResult, check_length, detect_prompt_injection

from supply_chain_agent.safety.harness import check_input_safety, check_output_safety

__all__ = ["GuardrailResult", "classify_input", "classify_output"]

MAX_INPUT_CHARS = 5000


def classify_input(text: str, max_chars: int = MAX_INPUT_CHARS) -> GuardrailResult:
    """Injection first, then sensitive identifiers, then length."""
    if (injection := detect_prompt_injection(text)) is not None:
        return injection
    harness = check_input_safety(text)
    if "prompt_injection_detected" in harness.reasons:
        return GuardrailResult(passed=False, category="prompt_injection", reasons=list(harness.reasons), score=0.9)
    if "sensitive_data_in_input" in harness.reasons:
        return GuardrailResult(passed=False, category="sensitive_data", reasons=list(harness.reasons), score=0.9)
    return check_length(text, max_chars) or GuardrailResult(passed=True)


def classify_output(text: str) -> GuardrailResult:
    check = check_output_safety(text)
    if check.passed:
        return GuardrailResult(passed=True)
    return GuardrailResult(passed=False, category="sensitive_output", reasons=list(check.reasons), score=0.9)
