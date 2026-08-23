from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.model_router import (
    ComplexityResult,
    CostTracker,
    LatencyTracker,
    ModelRouter,
    ModelTierConfig,
    classify_complexity,
)


class ClassifyComplexityTests(unittest.TestCase):
    def test_greeting_is_simple(self):
        r = classify_complexity("hello")
        self.assertEqual(r.tier, "simple")

    def test_short_statement_is_simple(self):
        r = classify_complexity("thanks")
        self.assertEqual(r.tier, "simple")

    def test_medication_query_is_moderate(self):
        r = classify_complexity("What medications does the patient take?")
        self.assertEqual(r.tier, "moderate")

    def test_lab_query_is_moderate(self):
        r = classify_complexity("Are there any abnormal lab results?")
        self.assertEqual(r.tier, "moderate")

    def test_vitals_query_is_moderate(self):
        r = classify_complexity("What is the patient blood pressure?")
        self.assertEqual(r.tier, "moderate")

    def test_claims_query_is_moderate(self):
        r = classify_complexity("Was the claim denied by the payer?")
        self.assertEqual(r.tier, "moderate")

    def test_polypharmacy_is_complex(self):
        r = classify_complexity("Analyze drug-drug interactions and contraindications for this polypharmacy patient")
        self.assertEqual(r.tier, "complex")

    def test_differential_diagnosis_is_complex(self):
        r = classify_complexity("What is the differential diagnosis given the lab trends over time?")
        self.assertEqual(r.tier, "complex")

    def test_risk_stratification_is_complex(self):
        r = classify_complexity("Risk stratify this patient for sepsis deterioration with trending vitals")
        self.assertEqual(r.tier, "complex")

    def test_multi_system_is_complex(self):
        r = classify_complexity("Assess renal and hepatic organ function given the comorbid conditions")
        self.assertEqual(r.tier, "complex")

    def test_simple_list_is_simple(self):
        r = classify_complexity("list active conditions")
        self.assertEqual(r.tier, "simple")

    def test_result_has_signals(self):
        r = classify_complexity("Explain the drug interaction risk")
        self.assertIn("drug_interaction_reasoning", r.signals)

    def test_result_score_is_nonnegative(self):
        r = classify_complexity("hello")
        self.assertGreaterEqual(r.score, 0)


class ModelTierConfigTests(unittest.TestCase):
    def test_from_env_uses_default_when_no_env(self):
        config = ModelTierConfig.from_env("llama3.2:3b")
        self.assertEqual(config.simple, "llama3.2:3b")
        self.assertEqual(config.moderate, "llama3.2:3b")
        self.assertEqual(config.complex, "llama3.2:3b")

    def test_is_uniform_when_all_same(self):
        config = ModelTierConfig(simple="m1", moderate="m1", complex="m1")
        self.assertTrue(config.is_uniform())

    def test_is_not_uniform_when_different(self):
        config = ModelTierConfig(simple="m1", moderate="m2", complex="m3")
        self.assertFalse(config.is_uniform())

    def test_model_for_tier(self):
        config = ModelTierConfig(simple="small", moderate="medium", complex="large")
        self.assertEqual(config.model_for_tier("simple"), "small")
        self.assertEqual(config.model_for_tier("moderate"), "medium")
        self.assertEqual(config.model_for_tier("complex"), "large")


class ModelRouterTests(unittest.TestCase):
    def _make_provider(self, response="test response"):
        provider = Mock()
        provider.generate.return_value = response
        provider.configured_model = "default-model"
        return provider

    def test_routes_simple_to_simple_model(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="small", moderate="medium", complex="large")
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        result = router.generate(prompt="test", timeout_seconds=60, max_tokens=100, question="hello")

        self.assertEqual(result, "test response")
        self.assertEqual(router.last_routing["tier"], "simple")
        self.assertEqual(router.last_routing["model"], "small")

    def test_routes_complex_to_complex_model(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="small", moderate="medium", complex="large")
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        result = router.generate(
            prompt="test", timeout_seconds=60, max_tokens=100,
            question="Analyze drug-drug interactions and contraindications with risk stratification",
        )

        self.assertEqual(router.last_routing["tier"], "complex")
        self.assertEqual(router.last_routing["model"], "large")

    def test_routes_to_named_provider(self):
        ollama = self._make_provider("ollama response")
        openai = self._make_provider("openai response")
        openai.model = "gpt-4.1-mini"
        config = ModelTierConfig(simple="ollama:small", moderate="ollama:medium", complex="openai:gpt-4.1")
        router = ModelRouter(
            providers={"ollama": ollama, "openai": openai},
            tier_config=config,
            default_provider_name="ollama",
        )

        result = router.generate(
            prompt="test", timeout_seconds=60, max_tokens=100,
            question="Assess differential diagnosis with comorbid renal hepatic conditions over time",
        )

        self.assertEqual(result, "openai response")
        openai.generate.assert_called_once()

    def test_restores_model_after_generate(self):
        provider = self._make_provider()
        provider.configured_model = "original-model"
        config = ModelTierConfig(simple="overridden", moderate="overridden", complex="overridden")
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        router.generate(prompt="test", timeout_seconds=60, max_tokens=100, question="hello")

        self.assertEqual(provider.configured_model, "original-model")

    def test_last_routing_includes_signals(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="s", moderate="m", complex="c")
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        router.generate(prompt="test", timeout_seconds=60, max_tokens=100, question="What medication does the patient take?")

        self.assertIn("signals", router.last_routing)
        self.assertIsInstance(router.last_routing["signals"], list)


class LatencyTrackerTests(unittest.TestCase):
    def test_empty_returns_zero(self):
        tracker = LatencyTracker()
        self.assertEqual(tracker.average_ms("complex"), 0.0)

    def test_records_and_averages(self):
        tracker = LatencyTracker(window=3)
        tracker.record("complex", 100)
        tracker.record("complex", 200)
        tracker.record("complex", 300)
        self.assertAlmostEqual(tracker.average_ms("complex"), 200.0)

    def test_exceeds_target(self):
        tracker = LatencyTracker()
        tracker.record("complex", 5000)
        self.assertTrue(tracker.exceeds_target("complex", 2000))

    def test_does_not_exceed_zero_target(self):
        tracker = LatencyTracker()
        tracker.record("complex", 99999)
        self.assertFalse(tracker.exceeds_target("complex", 0))


class CostTrackerTests(unittest.TestCase):
    def test_starts_at_zero(self):
        tracker = CostTracker()
        self.assertEqual(tracker.current_hourly_cost(), 0.0)

    def test_accumulates_cost(self):
        tracker = CostTracker()
        tracker.record("openai", 1000)
        self.assertGreater(tracker.current_hourly_cost(), 0.0)

    def test_ollama_is_free(self):
        tracker = CostTracker()
        tracker.record("ollama", 1000)
        self.assertEqual(tracker.current_hourly_cost(), 0.0)

    def test_exceeds_budget(self):
        tracker = CostTracker()
        tracker.record("openai", 1000000)
        self.assertTrue(tracker.exceeds_budget(0.01))

    def test_does_not_exceed_zero_budget(self):
        tracker = CostTracker()
        tracker.record("openai", 1000000)
        self.assertFalse(tracker.exceeds_budget(0))


class LatencyDowngradeTests(unittest.TestCase):
    def _make_provider(self, response="test response"):
        provider = Mock()
        provider.generate.return_value = response
        provider.configured_model = "default-model"
        return provider

    def test_downgrades_when_latency_exceeds_target(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="small", moderate="medium", complex="large", latency_target_ms=100)
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        # Simulate high latency for complex tier
        for _ in range(5):
            router.latency_tracker.record("complex", 5000)

        router.generate(
            prompt="test", timeout_seconds=60, max_tokens=100,
            question="Analyze drug-drug interactions and contraindications with risk stratification",
        )

        self.assertEqual(router.last_routing["original_tier"], "complex")
        self.assertEqual(router.last_routing["tier"], "moderate")
        self.assertTrue(router.last_routing["downgraded"])

    def test_no_downgrade_when_under_target(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="small", moderate="medium", complex="large", latency_target_ms=10000)
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        router.generate(
            prompt="test", timeout_seconds=60, max_tokens=100,
            question="Analyze drug-drug interactions and contraindications",
        )

        self.assertFalse(router.last_routing["downgraded"])

    def test_cost_budget_forces_downgrade(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="small", moderate="medium", complex="large", cost_budget_hourly_usd=0.001)
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        # Exhaust budget
        router.cost_tracker.record("openai", 1000000)

        router.generate(
            prompt="test", timeout_seconds=60, max_tokens=100,
            question="Analyze drug-drug interactions and contraindications with risk stratification",
        )

        self.assertTrue(router.last_routing["downgraded"])

    def test_routing_includes_latency_and_cost(self):
        provider = self._make_provider()
        config = ModelTierConfig(simple="s", moderate="m", complex="c")
        router = ModelRouter(providers={"ollama": provider}, tier_config=config, default_provider_name="ollama")

        router.generate(prompt="test", timeout_seconds=60, max_tokens=100, question="hello")

        self.assertIn("latency_ms", router.last_routing)
        self.assertIn("hourly_cost_usd", router.last_routing)
        self.assertIn("downgraded", router.last_routing)


if __name__ == "__main__":
    unittest.main()
