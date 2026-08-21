from __future__ import annotations

import unittest
from unittest.mock import Mock

import helpers  # noqa: F401

from app.graph_writes import merge_claim, merge_lab_signals, merge_reference_context


class GraphWritesTests(unittest.TestCase):
    def test_merge_lab_signals_noop_on_empty_signal_list(self):
        tx = Mock()

        merge_lab_signals(tx, "obs-1", [])

        tx.run.assert_not_called()

    def test_merge_lab_signals_threads_signals_into_query_params(self):
        tx = Mock()
        signals = [{"rule_id": "potassium_hyperkalemia", "condition": "Hyperkalemia", "reason": "elevated_potassium"}]

        merge_lab_signals(tx, "obs-2", signals)

        tx.run.assert_called_once()
        params = tx.run.call_args.args[1]
        self.assertEqual(params["obs_id"], "obs-2")
        self.assertEqual(params["signals"], signals)

    def test_merge_claim_threads_claim_mappings_and_outcomes(self):
        tx = Mock()
        event = {
            "patient_id": "patient-1",
            "event_id": "evt-claim-1",
            "event_ts": "2026-08-12T00:00:00Z",
            "source_type": "CLAIMS",
        }
        payload = {
            "claim_id": "claim-1",
            "payer": "payer-a",
            "procedure_code": "99291",
            "procedure_description": "Critical care",
            "diagnosis_code": "Z79.01",
            "status": "submitted",
            "claim_type": "institutional",
            "billed_amount": 100.0,
            "allowed_amount": 90.0,
            "service_date": "2026-08-12",
            "semantic": {
                "claim": {
                    "diagnosis_mapping": {"standard_system": "ICD10"},
                    "procedure_mapping": {"standard_system": "CPT", "display": "Critical care"},
                },
                "provenance": {"source_type": "claims"},
            },
        }
        outcomes = [{"rule_id": "institutional_claim_hospitalization", "adverse_outcome": "HO"}]

        merge_claim(tx, event, payload, outcomes)

        tx.run.assert_called_once()
        params = tx.run.call_args.args[1]
        self.assertEqual(params["claim_id"], "claim-1")
        self.assertEqual(params["diagnosis_standard_system"], "ICD10")
        self.assertEqual(params["procedure_standard_system"], "CPT")
        self.assertEqual(params["claim_outcomes"], outcomes)

    def test_merge_reference_context_threads_reference_semantic_mappings(self):
        tx = Mock()
        event = {"patient_id": "patient-1", "provider_id": "provider-1", "source_type": "REFERENCE"}
        payload = {
            "device_id": "device-1",
            "medication": "Lisinopril",
            "payer": "payer-a",
            "reference_data": {
                "patient": {"sex": "F", "risk_tier": "high", "name": "Patient A"},
                "provider": {"specialty": "cardiology", "name": "Dr A"},
                "device": {"device_type": "infusion_pump", "model": "X"},
                "medication": {"drug_class": "Antihypertensive", "safety_tier": "high-alert"},
                "payer": {"plan_type": "PPO", "network_tier": "in-network", "region": "west"},
            },
            "semantic": {
                "reference_context": {
                    "patient": {
                        "sex_mapping": {"standard_system": "HL7_ADMINISTRATIVE_SEX", "standard_code": "F", "display": "Female"},
                        "risk_tier_mapping": {"standard_system": "LOCAL_RISK_TIER", "standard_code": "high", "display": "High"},
                    },
                    "provider": {"specialty_mapping": {"standard_system": "NUCC_TAXONOMY_GROUPING", "standard_code": "TBD", "display": "Cardiology"}},
                    "device": {"device_type_mapping": {"standard_system": "LOCAL_DEVICE_TYPE", "standard_code": "infusion_pump", "display": "Infusion Pump"}},
                    "medication": {
                        "drug_class_mapping": {"standard_system": "LOCAL_DRUG_CLASS", "standard_code": "antihypertensive", "display": "Antihypertensive"},
                        "safety_tier_mapping": {"standard_system": "LOCAL_MEDICATION_SAFETY_TIER", "standard_code": "high_alert", "display": "High-Alert"},
                    },
                    "payer": {
                        "plan_type_mapping": {"standard_system": "LOCAL_PAYER_PLAN_TYPE", "standard_code": "PPO", "display": "PPO"},
                        "network_tier_mapping": {"standard_system": "LOCAL_NETWORK_TIER", "standard_code": "in-network", "display": "In-Network"},
                    },
                }
            },
        }

        merge_reference_context(tx, event, payload)

        tx.run.assert_called_once()
        params = tx.run.call_args.args[1]
        self.assertEqual(params["patient_sex_standard_system"], "HL7_ADMINISTRATIVE_SEX")
        self.assertEqual(params["patient_risk_tier_standard_code"], "high")
        self.assertEqual(params["provider_specialty_standard_system"], "NUCC_TAXONOMY_GROUPING")
        self.assertEqual(params["device_type_standard_code"], "infusion_pump")
        self.assertEqual(params["medication_safety_tier_standard_code"], "high_alert")
        self.assertEqual(params["payer_network_tier_standard_system"], "LOCAL_NETWORK_TIER")
