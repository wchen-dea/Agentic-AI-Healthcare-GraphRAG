"""Deterministic clinical output-safety rules shared by every answer path.

The engine classifies an answer as ``pass``, ``caveat_required`` or ``block``.
Rules are data (pattern, category, verdict) so they can be extended without
touching callers. An optional, provider-neutral classifier may escalate a
verdict to ``block`` but can never relax a deterministic block.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from agent_core.guardrails import GuardrailResult

__all__ = [
    "CAVEAT_TEXT",
    "ClinicalRule",
    "OutputClassifier",
    "OutputDecision",
    "apply_output_policy",
    "configure_output_classifier",
    "evaluate_output",
    "get_output_classifier",
    "has_safety_caveat",
]

Verdict = Literal["pass", "caveat_required", "block"]

CAVEAT_TEXT = (
    "Advisory only: this is not medical advice and requires clinical review "
    "by a qualified healthcare professional."
)

_NEGATION = re.compile(
    r"\b(not|never|avoid|without|don't|do\s+not|doesn't|shouldn't|cannot|can't)\b[^.!?\n]{0,30}$",
    re.I,
)
_SAFE_GUIDANCE = re.compile(r"\b(unless|until|without)\b[^.!?\n]{0,60}$", re.I)


@dataclass(frozen=True)
class ClinicalRule:
    name: str
    category: str
    pattern: re.Pattern[str]
    verdict: Literal["caveat_required", "block"]
    score: float
    negatable: bool = False


def _rule(
    name: str,
    category: str,
    pattern: str,
    verdict: Literal["caveat_required", "block"],
    score: float,
    *,
    negatable: bool = False,
) -> ClinicalRule:
    return ClinicalRule(name, category, re.compile(pattern, re.I), verdict, score, negatable)


RULES: tuple[ClinicalRule, ...] = (
    _rule("self_harm", "harmful_output",
          r"(kill|harm|hurt)\s+(yourself|the\s+patient|them)|you\s+(should|must|need\s+to)\s+die",
          "block", 0.95),
    _rule("stop_medication_directive", "harmful_output",
          r"\b(stop|quit|cease)\s+taking\s+(all\s+|any\s+|your\s+|the\s+)?(medications?|meds|medicine|"
          r"insulin|anticoagulants?|blood\s+thinners?|statins?|antibiotics?)\b"
          r"|\bdiscontinue\s+(all\s+|any\s+|your\s+|the\s+)(medications?|meds|medicine|insulin|"
          r"anticoagulants?|blood\s+thinners?|statins?|antibiotics?)\b"
          r"|\bno\s+longer\s+(need\s+to\s+)?take\s+(your|the|any)\s+(medications?|meds|medicine)\b"
          r"|\bskip\s+(your|the|all)\s+(medications?|meds|doses?)\b",
          "block", 0.95, negatable=True),
    _rule("unsupported_dosing_instruction", "unsafe_dosing",
          r"\b(double|triple|halve|increase|decrease|reduce)\s+(your|the)\s+(dose|dosage)\b"
          r"|\byou\s+(should|must|can|need\s+to)\s+(take|inject|administer)\s+\d+(\.\d+)?\s*"
          r"(mg|mcg|g|ml|units?|iu)\b"
          r"|\btake\s+\d+(\.\d+)?\s*(mg|mcg|g|ml|units?|iu)\s+(every|per|daily|twice|once|at\s+night|"
          r"in\s+the\s+morning)\b",
          "block", 0.9, negatable=True),
    _rule("sensitive_data_in_output", "sensitive_data",
          r"\b(social\s+security\s+number|ssn)\b|\bcredit\s+card\s+number\b|\bpassword\b.*\b(is|:)\s*\S+",
          "block", 0.9),
    _rule("clinical_directive_without_caveat", "missing_safety_caveat",
          r"\b(you\s+must|you\s+should\s+immediately|take\s+action\s+now|"
          r"you\s+(should|need\s+to)\s+(start|begin|switch\s+to)\s+(taking\s+)?\w+)\b",
          "caveat_required", 0.6),
)

_CAVEAT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.I)
    for p in (
        r"\bnot\s+(a\s+substitute\s+for\s+)?medical\s+advice\b",
        r"\bnot\s+a\s+substitute\b",
        r"\badvisory\b",
        r"\bclinical\s+(review|judg(e)?ment)\b",
        r"\bconsult\s+(with\s+)?(a|an|your|the)?\s*(qualified\s+|licensed\s+)?"
        r"(clinician|physician|doctor|pharmacist|provider|healthcare|health\s+care|nurse)\b",
        r"\bhealthcare\s+professional\b",
        r"\bdemo\s+data\b",
        r"\bsynthetic\s+(data|patient|record)",
        r"\bsafety\s+caveat\b",
    )
)


def has_safety_caveat(text: str) -> bool:
    """True when the text carries a recognised clinical-safety caveat phrase."""
    return any(p.search(text) for p in _CAVEAT_PATTERNS)


def _rule_matches(rule: ClinicalRule, text: str) -> bool:
    for match in rule.pattern.finditer(text):
        if rule.negatable:
            prefix = text[max(0, match.start() - 40): match.start()]
            if _NEGATION.search(prefix) or _SAFE_GUIDANCE.search(prefix):
                continue
        return True
    return False


class OutputClassifier(Protocol):
    """Optional provider-neutral model check; may only escalate to block."""

    def __call__(self, answer: str, evidence: Sequence[dict[str, Any]]) -> GuardrailResult: ...


_classifier: OutputClassifier | None = None


def configure_output_classifier(classifier: OutputClassifier | None) -> None:
    """Register (or clear) the optional classifier. Disabled by default."""
    global _classifier
    _classifier = classifier


def get_output_classifier() -> OutputClassifier | None:
    return _classifier


@dataclass(frozen=True)
class OutputDecision:
    verdict: Verdict
    category: str = ""
    reasons: tuple[str, ...] = ()
    score: float = 0.0
    text: str = ""

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"

    def to_guardrail_result(self) -> GuardrailResult:
        return GuardrailResult(
            passed=self.verdict != "block",
            category=self.category,
            reasons=list(self.reasons),
            score=self.score,
        )


def evaluate_output(
    text: str,
    *,
    evidence: Sequence[dict[str, Any]] = (),
    classifier: OutputClassifier | None | Callable[..., Any] = None,
) -> OutputDecision:
    """Classify an answer deterministically, then optionally escalate via a classifier."""
    blocks: list[ClinicalRule] = []
    caveats: list[ClinicalRule] = []
    for rule in RULES:
        if _rule_matches(rule, text):
            (blocks if rule.verdict == "block" else caveats).append(rule)

    if blocks:
        top = max(blocks, key=lambda r: r.score)
        return OutputDecision(
            "block", top.category, tuple(r.name for r in blocks), top.score, text
        )

    decision = OutputDecision("pass", "", (), 0.0, text)
    if caveats and not has_safety_caveat(text):
        top = max(caveats, key=lambda r: r.score)
        decision = OutputDecision(
            "caveat_required", top.category, tuple(r.name for r in caveats), top.score, text
        )

    classifier = classifier or _classifier
    if classifier is None:
        return decision
    try:
        verdict = classifier(text, evidence)
    except Exception:  # noqa: BLE001 - classifier failure must not alter the deterministic verdict
        return OutputDecision(
            decision.verdict,
            decision.category,
            (*decision.reasons, "classifier_error"),
            decision.score,
            text,
        )
    if not verdict.passed:
        return OutputDecision(
            "block",
            verdict.category or "classifier_block",
            (*decision.reasons, *verdict.reasons),
            max(decision.score, verdict.score),
            text,
        )
    return decision


def apply_output_policy(
    text: str,
    *,
    evidence: Sequence[dict[str, Any]] = (),
    classifier: OutputClassifier | None = None,
) -> OutputDecision:
    """Evaluate an answer and, for ``caveat_required``, return it with the standard caveat."""
    decision = evaluate_output(text, evidence=evidence, classifier=classifier)
    if decision.verdict == "caveat_required":
        return OutputDecision(
            "caveat_required",
            decision.category,
            decision.reasons,
            decision.score,
            f"{text.rstrip()}\n\n{CAVEAT_TEXT}",
        )
    return decision
