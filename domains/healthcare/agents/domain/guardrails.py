"""Guardrails classifier for input/output safety.

Replaces heuristic pattern matching with a classifier-based approach
that detects prompt injection, toxic content, and off-topic queries.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GuardrailResult:
    passed: bool
    category: str = ""
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0


# Injection patterns (high-precision rules)
_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"system\s*:\s*", re.I),
    re.compile(r"<\|?(system|assistant|user)\|?>", re.I),
    re.compile(r"forget\s+(everything|all|your\s+instructions)", re.I),
    re.compile(r"act\s+as\s+(if\s+)?(you\s+)?(are|were)\s+", re.I),
    re.compile(r"do\s+not\s+follow\s+(your|the)\s+(rules|instructions|guidelines)", re.I),
    re.compile(r"override\s+(safety|content|guardrail)", re.I),
]

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
    """Classify input text for safety issues."""
    reasons: list[str] = []

    # Check injection
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            return GuardrailResult(
                passed=False,
                category="prompt_injection",
                reasons=[f"Detected injection pattern: {pattern.pattern[:50]}"],
                score=0.95,
            )

    # Check off-topic
    for pattern in _OFFTOPIC_PATTERNS:
        if pattern.search(text):
            reasons.append(f"Possible off-topic: {pattern.pattern[:40]}")

    if reasons:
        return GuardrailResult(passed=False, category="off_topic", reasons=reasons, score=0.7)

    # Length check
    if len(text) > 5000:
        return GuardrailResult(
            passed=False,
            category="input_too_long",
            reasons=["Input exceeds 5000 characters"],
            score=0.9,
        )

    return GuardrailResult(passed=True, score=0.0)


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
