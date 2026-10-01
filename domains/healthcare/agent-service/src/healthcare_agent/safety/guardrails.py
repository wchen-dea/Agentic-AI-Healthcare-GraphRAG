"""Guardrails classifier for input/output safety.

Replaces heuristic pattern matching with a classifier-based approach
that detects prompt injection, toxic content, and off-topic queries.
"""
from __future__ import annotations

import re
from typing import Any

from agent_core.guardrails import (
    PROMPT_INJECTION_PATTERNS as _INJECTION_PATTERNS,
    GuardrailResult,
    check_length,
    detect_prompt_injection,
)

__all__ = ["GuardrailResult", "classify_grounding", "classify_input", "classify_output"]

_MAX_INPUT_CHARS = 5000

# Off-topic patterns for healthcare domain
_OFFTOPIC_PATTERNS = [
    re.compile(r"(write|generate|create)\s+(me\s+)?(a\s+)?(poem|story|song|essay|code)", re.I),
    re.compile(r"(how\s+to|teach\s+me)\s+(hack|exploit|break\s+into)", re.I),
    re.compile(r"(recipe|cook|bake)\s+", re.I),
]

# Output safety patterns
_OUTPUT_TOXIC_PATTERNS = [
    re.compile(r"(kill|harm|hurt)\s+(yourself|the\s+patient|them)", re.I),
    re.compile(r"stop\s+taking\s+(all|your)\s+medications?\s+(immediately|now|right\s+away)", re.I),
    re.compile(r"you\s+(should|must|need\s+to)\s+die", re.I),
]


def classify_input(text: str) -> GuardrailResult:
    """Classify input text: injection first, then healthcare topic scope, then length."""
    if (injection := detect_prompt_injection(text)) is not None:
        return injection

    reasons = [
        f"Possible off-topic: {pattern.pattern[:40]}"
        for pattern in _OFFTOPIC_PATTERNS
        if pattern.search(text)
    ]
    if reasons:
        return GuardrailResult(passed=False, category="off_topic", reasons=reasons, score=0.7)

    return check_length(text, _MAX_INPUT_CHARS) or GuardrailResult(passed=True, score=0.0)


def classify_output(text: str) -> GuardrailResult:
    """Classify output text for safety issues."""
    for pattern in _OUTPUT_TOXIC_PATTERNS:
        if pattern.search(text):
            return GuardrailResult(
                passed=False,
                category="harmful_output",
                reasons=[f"Detected harmful content: {pattern.pattern[:50]}"],
                score=0.95,
            )

    # Check if output contains clinical directives without safety caveat
    directive_patterns = [
        re.compile(r"(you\s+must|you\s+should\s+immediately|take\s+action\s+now)", re.I),
    ]
    for pattern in directive_patterns:
        if pattern.search(text) and "advisory" not in text.lower() and "clinical review" not in text.lower():
            return GuardrailResult(
                passed=False,
                category="missing_safety_caveat",
                reasons=["Clinical directive without safety caveat"],
                score=0.6,
            )

    return GuardrailResult(passed=True, score=0.0)


def classify_grounding(answer: str, evidence: list[dict[str, Any]]) -> GuardrailResult:
    """Check if the answer appears grounded in provided evidence."""
    if not evidence:
        return GuardrailResult(
            passed=True,
            category="no_evidence",
            reasons=["No evidence provided to check grounding against"],
            score=0.5,
        )

    # Extract key terms from evidence
    evidence_terms: set[str] = set()
    for item in evidence:
        for val in item.values():
            if isinstance(val, str) and len(val) > 3:
                evidence_terms.update(w.lower() for w in val.split() if len(w) > 3)

    # Check overlap between answer and evidence terms
    answer_words = {w.lower() for w in answer.split() if len(w) > 3}
    overlap = answer_words & evidence_terms
    coverage = len(overlap) / max(len(answer_words), 1)

    if coverage < 0.05 and len(answer) > 100:
        return GuardrailResult(
            passed=False,
            category="low_grounding",
            reasons=[f"Answer shares only {coverage:.0%} vocabulary with evidence"],
            score=1.0 - coverage,
        )

    return GuardrailResult(passed=True, score=coverage)
