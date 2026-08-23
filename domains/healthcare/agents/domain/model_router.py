"""Dynamic model routing based on query complexity.

Classifies queries into complexity tiers and routes to the appropriate
model. In dev all tiers default to the same model (zero config change).
In production, set LLM_MODEL_SIMPLE / LLM_MODEL_MODERATE / LLM_MODEL_COMPLEX
to route to different providers or model sizes.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Literal

ComplexityTier = Literal["simple", "moderate", "complex"]


@dataclass(frozen=True)
class ComplexityResult:
    tier: ComplexityTier
    score: int
    signals: list[str]


_SIMPLE_PATTERNS = re.compile(
    r"^(hi|hello|hey|thanks|help)$",
    re.IGNORECASE,
)

_SIMPLE_LIST = re.compile(
    r"^list .{1,40}$",
    re.IGNORECASE,
)

_COMPLEX_SIGNALS: list[tuple[re.Pattern, str, int]] = [
    (re.compile(r"\b(interact|polypharmacy|contraindic|drug.?drug|adverse.?event)", re.I), "drug_interaction_reasoning", 3),
    (re.compile(r"\b(differential|rule.?out|differential.?diagnosis)", re.I), "differential_diagnosis", 3),
    (re.compile(r"\b(risk.?stratif|acuity|triage|deteriorat|sepsis.?screen)", re.I), "risk_stratification", 2),
    (re.compile(r"\b(trend|over.?time|longitudinal|trajectory|time.?series)", re.I), "temporal_analysis", 2),
    (re.compile(r"\b(compare|versus|vs\.?|relative.?to|benchmark)", re.I), "comparative_analysis", 2),
    (re.compile(r"\b(comorbid|multi.?system|organ.?function|renal.*hepatic|hepatic.*renal|cardiac.*pulmonary)", re.I), "multi_system", 3),
    (re.compile(r"\b(explain|reason|why|justify|evidence.?for|rationale)", re.I), "explanation_depth", 1),
    (re.compile(r"\b(all|every|comprehensive|complete|full)", re.I), "breadth_request", 1),
]

_MODERATE_SIGNALS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bmedication|\bdrug|\bprescription|\bdose|\bdosage", re.I), "medication_query"),
    (re.compile(r"\blab|\bresult|\btest|\bpanel|\babnormal|\bcritical", re.I), "lab_query"),
    (re.compile(r"\bdiagnos|\bcondition|\bsymptom|\bicd|\bassessment", re.I), "diagnosis_query"),
    (re.compile(r"\bvital|heart.?rate|blood.?pressure|\bspo2|\btemperature", re.I), "vitals_query"),
    (re.compile(r"\bclaim|\bbilling|\bpayer|\bdenied|\bappeal|\bcoverage", re.I), "claims_query"),
    (re.compile(r"\bsummary|\boverview|\bstatus|\bupdate", re.I), "summary_request"),
]

COMPLEXITY_THRESHOLD_COMPLEX = 3
COMPLEXITY_THRESHOLD_MODERATE = 1


def classify_complexity(question: str) -> ComplexityResult:
    text = question.strip()

    if _SIMPLE_PATTERNS.match(text):
        return ComplexityResult(tier="simple", score=0, signals=["pattern_match_simple"])

    if _SIMPLE_LIST.match(text):
        return ComplexityResult(tier="simple", score=0, signals=["simple_list"])

    if len(text) < 15 and "?" not in text:
        return ComplexityResult(tier="simple", score=0, signals=["short_statement"])

    score = 0
    signals: list[str] = []

    for pattern, signal, weight in _COMPLEX_SIGNALS:
        if pattern.search(text):
            score += weight
            signals.append(signal)

    if score >= COMPLEXITY_THRESHOLD_COMPLEX:
        return ComplexityResult(tier="complex", score=score, signals=signals)

    for pattern, signal in _MODERATE_SIGNALS:
        if pattern.search(text):
            if signal not in signals:
                score += 1
                signals.append(signal)

    if score >= COMPLEXITY_THRESHOLD_MODERATE:
        return ComplexityResult(tier="moderate", score=score, signals=signals)

    return ComplexityResult(tier="simple", score=score, signals=signals or ["no_domain_signals"])


@dataclass(frozen=True)
class ModelTierConfig:
    """Maps complexity tiers to model identifiers (provider:model or just model)."""
    simple: str
    moderate: str
    complex: str

    def model_for_tier(self, tier: ComplexityTier) -> str:
        return getattr(self, tier)

    @staticmethod
    def from_env(default_model: str) -> ModelTierConfig:
        return ModelTierConfig(
            simple=os.getenv("LLM_MODEL_SIMPLE", default_model),
            moderate=os.getenv("LLM_MODEL_MODERATE", default_model),
            complex=os.getenv("LLM_MODEL_COMPLEX", default_model),
        )

    def is_uniform(self) -> bool:
        return self.simple == self.moderate == self.complex


class ModelRouter:
    """Selects model based on query complexity, delegates to underlying providers."""

    def __init__(self, *, providers: dict[str, Any], tier_config: ModelTierConfig, default_provider_name: str) -> None:
        self.providers = providers
        self.tier_config = tier_config
        self.default_provider_name = default_provider_name
        self._last_routing: dict[str, Any] | None = None

    def _resolve_provider_and_model(self, model_spec: str) -> tuple[Any, str]:
        if ":" in model_spec and model_spec.split(":", 1)[0] in self.providers:
            provider_name, model_name = model_spec.split(":", 1)
            return self.providers[provider_name], model_name
        return self.providers[self.default_provider_name], model_spec

    def generate(
        self,
        *,
        prompt: str,
        timeout_seconds: int,
        max_tokens: int,
        temperature: float = 0.2,
        question: str = "",
    ) -> str:
        complexity = classify_complexity(question or prompt[:200])
        model_spec = self.tier_config.model_for_tier(complexity.tier)
        provider, model_override = self._resolve_provider_and_model(model_spec)

        if hasattr(provider, "configured_model"):
            original_model = provider.configured_model
            provider.configured_model = model_override
        elif hasattr(provider, "model"):
            original_model = provider.model
            provider.model = model_override
        else:
            original_model = None

        self._last_routing = {
            "tier": complexity.tier,
            "score": complexity.score,
            "signals": complexity.signals,
            "model": model_spec,
        }

        try:
            result = provider.generate(
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        finally:
            if original_model is not None:
                if hasattr(provider, "configured_model"):
                    provider.configured_model = original_model
                elif hasattr(provider, "model"):
                    provider.model = original_model

        return result

    @property
    def last_routing(self) -> dict[str, Any] | None:
        return self._last_routing
