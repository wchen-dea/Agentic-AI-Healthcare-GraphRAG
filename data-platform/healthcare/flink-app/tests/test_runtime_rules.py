from __future__ import annotations

import unittest
from unittest.mock import Mock

from helpers import (
    evaluate_claims_outcome_rules,
    evaluate_lab_signal_rules,
    load_claims_outcome_rules,
    load_lab_signal_rules,
    load_ontology_bundle,
    load_processor_module,
    normalize_event_payload,
)


class RuntimeRulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_ontology_bundle()
        cls.lab_rules = load_lab_signal_rules(cls.bundle)
        cls.claim_rules = load_claims_outcome_rules(cls.bundle)

    def test_lab_threshold_regression_cases(self):
        self.assertEqual(
            evaluate_lab_signal_rules(self.lab_rules, "Potassium", 5.5),
            [{"rule_id": "potassium_hyperkalemia", "condition": "Hyperkalemia", "reason": "elevated_potassium"}],
        )
        self.assertEqual(
            evaluate_lab_signal_rules(self.lab_rules, "TSH", 0.4),
            [{"rule_id": "tsh_hyperthyroidism", "condition": "Hyperthyroidism", "reason": "low_tsh"}],
        )
        self.assertEqual(evaluate_lab_signal_rules(self.lab_rules, "Sodium", 142), [])

    def test_claims_outcome_regression_cases(self):
        self.assertEqual(
            evaluate_claims_outcome_rules(
                self.claim_rules,
                event_type="CLAIM_STATUS",
                claim_type="institutional",
                procedure_code=None,
            ),
            [{"rule_id": "institutional_claim_hospitalization", "type": "RESULTED_IN", "adverse_outcome": "HO"}],
        )
        self.assertEqual(
            evaluate_claims_outcome_rules(
                self.claim_rules,
                event_type="CLAIM_STATUS",
                claim_type="professional",
                procedure_code="99291",
            ),
            [{"rule_id": "hospital_cpt_hospitalization", "type": "RESULTED_IN", "adverse_outcome": "HO"}],
        )

    def test_processor_merge_lab_signals_uses_yaml_rules(self):
        module = load_processor_module()
        tx = Mock()
        signals = evaluate_lab_signal_rules(self.lab_rules, "Potassium", 5.8)

        module.HealthcareGraphRagProcessor.merge_lab_signals(tx, "obs-1", signals)

        tx.run.assert_called_once()
        params = tx.run.call_args.args[1]
        self.assertEqual(
            params["signals"],
            [{"rule_id": "potassium_hyperkalemia", "condition": "Hyperkalemia", "reason": "elevated_potassium"}],
        )

    def test_normalize_event_payload_adds_semantic_fields(self):
        event = {"event_type": "LAB_RESULT", "source_type": "lab"}
        payload = {"lab_name": " glucose ", "value": 185, "unit": "mg/dL"}
        normalized_event, normalized_payload = normalize_event_payload(event, payload, self.bundle)
        self.assertEqual(normalized_event["source_type"], "LAB")
        self.assertEqual(normalized_payload["lab_name"], "Glucose")
        self.assertEqual(normalized_payload["semantic"]["observation"]["mapping"]["standard_system"], "LOINC")

    def test_normalize_medication_and_claim_fields(self):
        event = {"event_type": "MEDICATION_ORDER", "source_type": "pharmacy"}
        payload = {"medication": " lisinopril ", "claim_type": " Institutional "}
        normalized_event, normalized_payload = normalize_event_payload(event, payload, self.bundle)
        self.assertEqual(normalized_event["source_type"], "PHARMACY")
        self.assertEqual(normalized_payload["medication"], "Lisinopril")
        self.assertEqual(normalized_payload["claim_type"], "institutional")

    def test_normalize_clinical_note_and_claim_semantics(self):
        event = {"event_type": "CLINICAL_NOTE", "source_type": "ehr"}
        payload = {"diagnosis": " diabetes mellitus ", "symptom": " Cough ", "icd10_code": " e11.9 "}
        normalized_event, normalized_payload = normalize_event_payload(event, payload, self.bundle)
        self.assertEqual(normalized_event["source_type"], "EHR")
        self.assertEqual(normalized_payload["diagnosis"], "Diabetes Mellitus")
        self.assertEqual(normalized_payload["symptom"], "cough")
        self.assertEqual(normalized_payload["icd10_code"], "E11.9")

    def test_normalize_claim_semantics(self):
        event = {"event_type": "CLAIM_STATUS", "source_type": "claims"}
        payload = {"diagnosis_code": " z79.01 ", "procedure_code": " 99291 ", "procedure_description": "Critical care"}
        _, normalized_payload = normalize_event_payload(event, payload, self.bundle)
        self.assertEqual(normalized_payload["diagnosis_code"], "Z79.01")
        self.assertEqual(normalized_payload["procedure_code"], "99291")

    def test_normalize_reference_enrichments(self):
        event = {"event_type": "MEDICATION_ORDER", "source_type": "pharmacy"}
        payload = {
            "medication": " lisinopril ",
            "reference_data": {
                "patient": {"sex": " f ", "risk_tier": " High "},
                "provider": {"specialty": " cardiology "},
                "device": {"device_type": " infusion_pump "},
                "medication": {"drug_class": " Antihypertensive ", "safety_tier": " High-Alert "},
                "payer": {"plan_type": " PPO ", "network_tier": " In-Network "},
            },
        }
        _, normalized_payload = normalize_event_payload(event, payload, self.bundle)
        ref_semantics = normalized_payload["semantic"]["reference_context"]
        self.assertEqual(ref_semantics["patient"]["sex_mapping"]["standard_system"], "HL7_ADMINISTRATIVE_SEX")
        self.assertEqual(ref_semantics["patient"]["risk_tier_mapping"]["standard_code"], "high")
        self.assertEqual(ref_semantics["provider"]["specialty_mapping"]["standard_system"], "NUCC_TAXONOMY_GROUPING")
        self.assertEqual(ref_semantics["device"]["device_type_mapping"]["standard_code"], "infusion_pump")
        self.assertEqual(ref_semantics["medication"]["drug_class_mapping"]["standard_code"], "antihypertensive")
        self.assertEqual(ref_semantics["medication"]["safety_tier_mapping"]["standard_code"], "high_alert")
        self.assertEqual(ref_semantics["payer"]["plan_type_mapping"]["standard_code"], "PPO")
        self.assertEqual(ref_semantics["payer"]["network_tier_mapping"]["standard_code"], "in-network")

    def test_merge_lab_result_threads_mapping_fields(self):
        module = load_processor_module()
        tx = Mock()
        event = {"patient_id": "patient-1", "event_id": "evt-1", "event_ts": "2026-08-12T00:00:00Z", "source_type": "LAB"}
        payload = {
            "lab_name": "Glucose", "value": 185, "unit": "mg/dL", "abnormal": True,
            "lab_panel": "BMP", "specimen_type": "serum",
            "semantic": {"observation": {"mapping": {"standard_system": "LOINC", "standard_code": "TBD", "display": "Glucose [Mass/volume] in Blood"}}, "provenance": {"trust_level": "high"}},
        }
        module.HealthcareGraphRagProcessor.merge_lab_result(tx, event, payload)
        params = tx.run.call_args.args[1]
        self.assertEqual(params["standard_system"], "LOINC")

    def test_merge_medication_order_threads_mapping_fields(self):
        module = load_processor_module()
        tx = Mock()
        event = {"patient_id": "patient-1", "event_id": "evt-2", "event_ts": "2026-08-12T00:00:00Z", "source_type": "PHARMACY"}
        payload = {
            "medication": "Lisinopril", "drug_class": "ACE inhibitor", "dose": "10mg", "route": "oral",
            "frequency": "daily", "order_type": "maintenance", "days_supply": 30,
            "semantic": {"medication": {"mapping": {"standard_system": "RxNorm", "standard_code": "TBD", "display": "Lisinopril"}}, "provenance": {"trust_level": "high"}},
        }
        module.HealthcareGraphRagProcessor.merge_medication_order(tx, event, payload)
        params = tx.run.call_args.args[1]
        self.assertEqual(params["standard_system"], "RxNorm")

    def test_merge_clinical_note_threads_mapping_fields(self):
        module = load_processor_module()
        tx = Mock()
        event = {"patient_id": "patient-1", "event_id": "evt-3", "event_ts": "2026-08-12T00:00:00Z", "source_type": "EHR"}
        payload = {
            "diagnosis": "Diabetes Mellitus", "symptom": "cough", "icd10_code": "E11.9",
            "semantic": {
                "condition": {"mapping": {"standard_system": "SNOMED_CT", "standard_code": "TBD", "display": "Diabetes mellitus"}},
                "symptom": {"mapping": {"standard_system": "MedDRA", "standard_code": "TBD", "display": "Cough"}},
                "provenance": {"trust_level": "high"},
            },
        }
        module.HealthcareGraphRagProcessor.merge_clinical_note(tx, event, payload)
        params = tx.run.call_args.args[1]
        self.assertEqual(params["condition_standard_system"], "SNOMED_CT")
        self.assertEqual(params["symptom_standard_system"], "MedDRA")

    def test_merge_claim_threads_mapping_fields(self):
        module = load_processor_module()
        tx = Mock()
        event = {"patient_id": "patient-1", "event_id": "evt-4", "event_ts": "2026-08-12T00:00:00Z", "source_type": "CLAIMS"}
        payload = {
            "claim_id": "claim-1", "payer": "payer-a", "procedure_code": "99291", "procedure_description": "Critical care",
            "diagnosis_code": "Z79.01", "status": "submitted", "claim_type": "institutional", "billed_amount": 100.0,
            "allowed_amount": 90.0, "service_date": "2026-08-12",
            "semantic": {"claim": {"diagnosis_mapping": {"standard_system": "ICD10", "standard_code": "Z79.01", "display": "Z79.01"}, "procedure_mapping": {"standard_system": "CPT", "standard_code": "99291", "display": "Critical care"}}, "provenance": {"trust_level": "medium"}},
        }
        module.HealthcareGraphRagProcessor.merge_claim(tx, event, payload, [{"rule_id": "institutional_claim_hospitalization", "adverse_outcome": "HO"}])
        params = tx.run.call_args.args[1]
        self.assertEqual(params["diagnosis_standard_system"], "ICD10")
        self.assertEqual(params["procedure_standard_system"], "CPT")

    def test_merge_reference_context_threads_mapping_fields(self):
        module = load_processor_module()
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
        module.HealthcareGraphRagProcessor.merge_reference_context(tx, event, payload)
        params = tx.run.call_args.args[1]
        self.assertEqual(params["patient_sex_standard_system"], "HL7_ADMINISTRATIVE_SEX")
        self.assertEqual(params["patient_risk_tier_standard_code"], "high")
        self.assertEqual(params["provider_specialty_standard_system"], "NUCC_TAXONOMY_GROUPING")
        self.assertEqual(params["device_type_standard_code"], "infusion_pump")
        self.assertEqual(params["medication_drug_class_standard_code"], "antihypertensive")
        self.assertEqual(params["medication_safety_tier_standard_code"], "high_alert")
        self.assertEqual(params["payer_network_tier_standard_system"], "LOCAL_NETWORK_TIER")
