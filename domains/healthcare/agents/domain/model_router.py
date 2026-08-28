"""Dynamic model routing based on query complexity, latency, and cost.

Classifies queries into complexity tiers and routes to the appropriate
model. Tracks per-tier latency and enforces cost budgets.

In dev all tiers default to the same model (zero config change).
In production, set LLM_MODEL_SIMPLE / LLM_MODEL_MODERATE / LLM_MODEL_COMPLEX
to route to different providers or model sizes.

Latency-based routing: if a tier's rolling average latency exceeds
LATENCY_TARGET_MS, the router downgrades to the next cheaper tier.

Cost tracking: each request estimates token cost and accumulates against
a configurable hourly budget (COST_BUDGET_HOURLY_USD).
"""
from __future__ import annotations

import os
import re
import time
from collections import deque
from dataclasses import dataclass, field
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
    latency_target_ms: float = 0.0
    cost_budget_hourly_usd: float = 0.0

    def model_for_tier(self, tier: ComplexityTier) -> str:
        return getattr(self, tier)

    @staticmethod
    def from_env(default_model: str) -> ModelTierConfig:
        return ModelTierConfig(
            simple=os.getenv("LLM_MODEL_SIMPLE", default_model),
            moderate=os.getenv("LLM_MODEL_MODERATE", default_model),
            complex=os.getenv("LLM_MODEL_COMPLEX", default_model),
            latency_target_ms=float(os.getenv("LLM_LATENCY_TARGET_MS", "0")),
            cost_budget_hourly_usd=float(os.getenv("LLM_COST_BUDGET_HOURLY_USD", "0")),
        )

    def is_uniform(self) -> bool:
        return self.simple == self.moderate == self.complex


# Per-token cost estimates (USD) by provider prefix
_DEFAULT_COST_PER_TOKEN: dict[str, float] = {
    "openai": 0.000015,
    "anthropic": 0.000015,
    "bedrock": 0.000015,
    "ollama": 0.0,
}

_TIER_DOWNGRADE: dict[ComplexityTier, ComplexityTier] = {
    "complex": "moderate",
    "moderate": "simple",
    "simple": "simple",
}


class LatencyTracker:
    """Rolling average latency per tier."""

    def __init__(self, window: int = 20):
        self._window = window
        self._samples: dict[str, deque[float]] = {}

    def record(self, tier: str, latency_ms: float) -> None:
        if tier not in self._samples:
            self._samples[tier] = deque(maxlen=self._window)
        self._samples[tier].append(latency_ms)

    def average_ms(self, tier: str) -> float:
        samples = self._samples.get(tier)
        if not samples:
            return 0.0
        return sum(samples) / len(samples)

    def exceeds_target(self, tier: str, target_ms: float) -> bool:
        if target_ms <= 0:
            return False
        return self.average_ms(tier) > target_ms


class CostTracker:
    """Hourly cost accumulator with budget enforcement."""

    def __init__(self):
        self._hour_start: float = time.time()
        self._hour_cost: float = 0.0

    def _maybe_reset(self) -> None:
        now = time.time()
        if now - self._hour_start >= 3600:
            self._hour_start = now
            self._hour_cost = 0.0

    def record(self, provider_prefix: str, token_count: int) -> None:
        self._maybe_reset()
        cost_per_token = _DEFAULT_COST_PER_TOKEN.get(provider_prefix, 0.000010)
        self._hour_cost += cost_per_token * token_count

    def current_hourly_cost(self) -> float:
        self._maybe_reset()
        return self._hour_cost

    def exceeds_budget(self, budget_usd: float) -> bool:
        if budget_usd <= 0:
            return False
        self._maybe_reset()
        return self._hour_cost >= budget_usd


class ModelRouter:
    """Selects model based on query complexity, latency, and cost budget."""

    def __init__(self, *, providers: dict[str, Any], tier_config: ModelTierConfig, default_provider_name: str) -> None:
        self.providers = providers
        self.tier_config = tier_config
        self.default_provider_name = default_provider_name
        self._last_routing: dict[str, Any] | None = None
        self.latency_tracker = LatencyTracker()
        self.cost_tracker = CostTracker()

    def _resolve_provider_and_model(self, model_spec: str) -> tuple[Any, str]:
        if ":" in model_spec and model_spec.split(":", 1)[0] in self.providers:
            provider_name, model_name = model_spec.split(":", 1)
            return self.providers[provider_name], model_name
        return self.providers[self.default_provider_name], model_spec

    def _provider_prefix(self, model_spec: str) -> str:
        if ":" in model_spec:
            return model_spec.split(":", 1)[0]
        return self.default_provider_name

    def _get_provider_model(self, provider: Any) -> str | None:
        target = getattr(provider, "primary", provider)
        if hasattr(target, "configured_model"):
            return target.configured_model
        if hasattr(target, "model"):
            return target.model
        return None

    def _set_provider_model(self, provider: Any, model: str) -> None:
        target = getattr(provider, "primary", provider)
        if hasattr(target, "configured_model"):
            target.configured_model = model
        elif hasattr(target, "model"):
            target.model = model

    def _maybe_downgrade_tier(self, tier: ComplexityTier) -> ComplexityTier:
        """Downgrade tier if latency target exceeded or cost budget exhausted."""
        effective = tier
        if self.latency_tracker.exceeds_target(effective, self.tier_config.latency_target_ms):
            effective = _TIER_DOWNGRADE[effective]
        if self.cost_tracker.exceeds_budget(self.tier_config.cost_budget_hourly_usd):
            effective = _TIER_DOWNGRADE.get(effective, "simple")
        return effective

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
        original_tier = complexity.tier
        effective_tier = self._maybe_downgrade_tier(original_tier)
        model_spec = self.tier_config.model_for_tier(effective_tier)
        provider, model_override = self._resolve_provider_and_model(model_spec)

        original_model = self._get_provider_model(provider)
        if original_model is not None:
            self._set_provider_model(provider, model_override)

        start_ms = time.time() * 1000

        try:
            result = provider.generate(
                prompt=prompt,
                timeout_seconds=timeout_seconds,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        finally:
            if original_model is not None:
                self._set_provider_model(provider, original_model)

        latency_ms = time.time() * 1000 - start_ms
        self.latency_tracker.record(effective_tier, latency_ms)

        token_estimate = max(len(result.split()), 1) if not result.startswith("LLM error:") else 0
        self.cost_tracker.record(self._provider_prefix(model_spec), token_estimate)

        self._last_routing = {
            "tier": effective_tier,
            "original_tier": original_tier,
            "downgraded": effective_tier != original_tier,
            "score": complexity.score,
            "signals": complexity.signals,
            "model": model_spec,
            "latency_ms": round(latency_ms, 1),
            "hourly_cost_usd": round(self.cost_tracker.current_hourly_cost(), 6),
        }

        return result

    @property
    def last_routing(self) -> dict[str, Any] | None:
        return self._last_routing
