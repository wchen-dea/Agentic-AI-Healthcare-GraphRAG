"""Guardrail result type and domain-neutral checks.

Domain services compose these with their own topic and output-safety rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class GuardrailResult:
    passed: bool
    category: str = ""
    reasons: list[str] = field(default_factory=list)
    score: float = 0.0


class TextGuardrail(Protocol):
    def __call__(self, text: str) -> GuardrailResult: ...


PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts|rules)", re.I),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.I),
    re.compile(r"system\s*:\s*", re.I),
    re.compile(r"<\|?(system|assistant|user)\|?>", re.I),
    re.compile(r"forget\s+(everything|all|your\s+instructions)", re.I),
    re.compile(r"act\s+as\s+(if\s+)?(you\s+)?(are|were)\s+", re.I),
    re.compile(r"do\s+not\s+follow\s+(your|the)\s+(rules|instructions|guidelines)", re.I),
    re.compile(r"override\s+(safety|content|guardrail)", re.I),
)


def detect_prompt_injection(text: str) -> GuardrailResult | None:
    """Return a blocking result if ``text`` matches a known injection pattern."""
    for pattern in PROMPT_INJECTION_PATTERNS:
        if pattern.search(text):
            return GuardrailResult(
                passed=False,
                category="prompt_injection",
                reasons=[f"Detected injection pattern: {pattern.pattern[:50]}"],
                score=0.95,
            )
    return None


def check_length(text: str, max_chars: int) -> GuardrailResult | None:
    """Return a blocking result if ``text`` exceeds ``max_chars``."""
    if len(text) > max_chars:
        return GuardrailResult(
            passed=False,
            category="input_too_long",
            reasons=[f"Input exceeds {max_chars} characters"],
            score=0.9,
        )
    return None
