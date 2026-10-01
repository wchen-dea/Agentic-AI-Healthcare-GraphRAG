"""Build the LLM gateway (primary, fallback, and tiered router) from settings."""
from __future__ import annotations

from typing import Any

from healthcare_agent.config.settings import HealthcareAgentSettings
from healthcare_agent.generation.model_router import ModelRouter, ModelTierConfig
from healthcare_agent.generation.providers import FallbackProvider, create_provider


def tier_config_from_settings(settings: HealthcareAgentSettings) -> ModelTierConfig:
    return ModelTierConfig(
        simple=settings.llm_model_simple or settings.llm_model,
        moderate=settings.llm_model_moderate or settings.llm_model,
        complex=settings.llm_model_complex or settings.llm_model,
        latency_target_ms=settings.llm_latency_target_ms,
        cost_budget_hourly_usd=settings.llm_cost_budget_hourly_usd,
    )


def build_llm_provider(settings: HealthcareAgentSettings) -> Any:
    """Primary provider, wrapped with a fallback and a tier router when configured.

    Tier models use ``provider:model`` specs; each extra provider is created once.
    """
    provider: Any = create_provider(
        settings.llm_provider, base_url=settings.ollama_url, configured_model=settings.llm_model
    )
    if settings.llm_fallback_provider:
        fallback = create_provider(
            settings.llm_fallback_provider,
            base_url=settings.ollama_url,
            configured_model=settings.llm_fallback_model,
        )
        provider = FallbackProvider(provider, fallback)

    tier_config = tier_config_from_settings(settings)
    if tier_config.is_uniform():
        return provider

    providers: dict[str, Any] = {settings.llm_provider: provider}
    for spec in (tier_config.simple, tier_config.moderate, tier_config.complex):
        if ":" not in spec:
            continue
        name, model = spec.split(":", 1)
        if name not in providers:
            providers[name] = create_provider(name, base_url=settings.ollama_url, configured_model=model)
    return ModelRouter(providers=providers, tier_config=tier_config, default_provider_name=settings.llm_provider)


def llm_model_info(provider: Any, settings: HealthcareAgentSettings) -> dict[str, Any]:
    """Resolve which provider/model/tier served the last ``generate()`` call."""
    routing = getattr(provider, "last_routing", None)
    if routing:
        return {
            "llm_provider": settings.llm_provider,
            "llm_model": routing.get("model", settings.llm_model),
            "llm_tier": routing.get("tier", ""),
            "llm_downgraded": routing.get("downgraded", False),
        }
    target = getattr(provider, "primary", provider)
    model = getattr(target, "configured_model", None) or getattr(target, "model", None) or settings.llm_model
    return {"llm_provider": settings.llm_provider, "llm_model": model}
