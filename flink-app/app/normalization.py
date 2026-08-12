from __future__ import annotations

from typing import Any

from app.ontology_loader import provenance_for_source_type, vocabulary_mapping_index


def _normalize_whitespace(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(str(value).strip().split())
    return normalized or None


def _title_case(value: str | None) -> str | None:
    normalized = _normalize_whitespace(value)
    if normalized is None:
        return None
    return normalized.title()


def _mapping_record(index: dict[str, dict[str, Any]], local_code: str | None) -> dict[str, Any] | None:
    normalized = _normalize_whitespace(local_code)
    if normalized is None:
        return None
    item = index.get(normalized.casefold())
    if not item:
        return None
    return {
        "local_code": normalized,
        "standard_system": item.get("standard_system"),
        "standard_code": item.get("standard_code"),
        "display": item.get("display"),
    }


def normalize_event_payload(
    event: dict[str, Any],
    payload: dict[str, Any],
    ontology_bundle: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_type = _normalize_whitespace(event.get("source_type"))
    if source_type:
        event["source_type"] = source_type.upper()

    semantics = dict(payload.get("semantic", {}))
    lab_index = vocabulary_mapping_index(ontology_bundle, "labs")
    medication_index = vocabulary_mapping_index(ontology_bundle, "medications")
    symptom_index = vocabulary_mapping_index(ontology_bundle, "adverse_reactions")
    condition_index = vocabulary_mapping_index(ontology_bundle, "conditions")
    patient_risk_tier_index = vocabulary_mapping_index(ontology_bundle, "patient_risk_tiers")
    patient_sex_index = vocabulary_mapping_index(ontology_bundle, "patient_sex")
    medication_drug_class_index = vocabulary_mapping_index(ontology_bundle, "medication_drug_classes")
    medication_safety_tier_index = vocabulary_mapping_index(ontology_bundle, "medication_safety_tiers")
    provider_specialty_index = vocabulary_mapping_index(ontology_bundle, "provider_specialties")
    device_type_index = vocabulary_mapping_index(ontology_bundle, "device_types")
    payer_plan_type_index = vocabulary_mapping_index(ontology_bundle, "payer_plan_types")
    payer_network_tier_index = vocabulary_mapping_index(ontology_bundle, "payer_network_tiers")

    event_type = event.get("event_type")
    if event_type == "LAB_RESULT":
        observation_name = _title_case(payload.get("lab_name"))
        if observation_name:
            payload["lab_name"] = observation_name
        semantics["observation"] = {
            "name": observation_name,
            "mapping": _mapping_record(lab_index, observation_name),
        }
    elif event_type == "MEDICATION_ORDER":
        medication_name = _title_case(payload.get("medication"))
        if medication_name:
            payload["medication"] = medication_name
        semantics["medication"] = {
            "name": medication_name,
            "mapping": _mapping_record(medication_index, medication_name),
        }
    elif event_type == "CLINICAL_NOTE":
        symptom_name = _normalize_whitespace(payload.get("symptom"))
        if symptom_name:
            payload["symptom"] = symptom_name.casefold()
        diagnosis = _title_case(payload.get("diagnosis"))
        if diagnosis:
            payload["diagnosis"] = diagnosis
        icd10_code = _normalize_whitespace(payload.get("icd10_code"))
        if icd10_code:
            payload["icd10_code"] = icd10_code.upper()
        semantics["symptom"] = {
            "name": payload.get("symptom"),
            "mapping": _mapping_record(symptom_index, payload.get("symptom")),
        }
        semantics["condition"] = {
            "name": payload.get("diagnosis"),
            "mapping": _mapping_record(condition_index, payload.get("diagnosis")),
        }
    elif event_type == "CLAIM_STATUS":
        diagnosis_code = _normalize_whitespace(payload.get("diagnosis_code"))
        if diagnosis_code:
            payload["diagnosis_code"] = diagnosis_code.upper()
        procedure_code = _normalize_whitespace(payload.get("procedure_code"))
        if procedure_code:
            payload["procedure_code"] = procedure_code.upper()
        semantics["claim"] = {
            "diagnosis_mapping": {
                "standard_system": "ICD10",
                "standard_code": payload.get("diagnosis_code"),
                "display": payload.get("diagnosis_code"),
            }
            if payload.get("diagnosis_code")
            else None,
            "procedure_mapping": {
                "standard_system": "CPT",
                "standard_code": payload.get("procedure_code"),
                "display": payload.get("procedure_description"),
            }
            if payload.get("procedure_code")
            else None,
        }

    claim_type = _normalize_whitespace(payload.get("claim_type"))
    if claim_type:
        payload["claim_type"] = claim_type.lower()

    reference_data = payload.get("reference_data") or {}
    if reference_data:
        reference_semantics = dict(semantics.get("reference_context", {}))

        patient_ref = reference_data.get("patient") or {}
        patient_sex = _normalize_whitespace(patient_ref.get("sex"))
        if patient_sex:
            patient_ref["sex"] = patient_sex.upper()
        risk_tier = _normalize_whitespace(patient_ref.get("risk_tier"))
        if risk_tier:
            patient_ref["risk_tier"] = risk_tier.lower()
        reference_semantics["patient"] = {
            "sex_mapping": _mapping_record(patient_sex_index, patient_ref.get("sex")),
            "risk_tier_mapping": _mapping_record(patient_risk_tier_index, patient_ref.get("risk_tier")),
        }

        provider_ref = reference_data.get("provider") or {}
        provider_specialty = _normalize_whitespace(provider_ref.get("specialty"))
        if provider_specialty:
            provider_ref["specialty"] = provider_specialty
        reference_semantics["provider"] = {
            "specialty_mapping": _mapping_record(provider_specialty_index, provider_specialty),
        }

        device_ref = reference_data.get("device") or {}
        device_type = _normalize_whitespace(device_ref.get("device_type"))
        if device_type:
            device_ref["device_type"] = device_type.lower()
        reference_semantics["device"] = {
            "device_type_mapping": _mapping_record(device_type_index, device_ref.get("device_type")),
        }

        medication_ref = reference_data.get("medication") or {}
        drug_class = _normalize_whitespace(medication_ref.get("drug_class"))
        if drug_class:
            medication_ref["drug_class"] = drug_class
        safety_tier = _normalize_whitespace(medication_ref.get("safety_tier"))
        if safety_tier:
            medication_ref["safety_tier"] = safety_tier.lower()
        reference_semantics["medication"] = {
            "drug_class_mapping": _mapping_record(medication_drug_class_index, medication_ref.get("drug_class")),
            "safety_tier_mapping": _mapping_record(medication_safety_tier_index, medication_ref.get("safety_tier")),
        }

        payer_ref = reference_data.get("payer") or {}
        plan_type = _normalize_whitespace(payer_ref.get("plan_type"))
        if plan_type:
            payer_ref["plan_type"] = plan_type
        network_tier = _normalize_whitespace(payer_ref.get("network_tier"))
        if network_tier:
            payer_ref["network_tier"] = network_tier.lower()
        reference_semantics["payer"] = {
            "plan_type_mapping": _mapping_record(payer_plan_type_index, payer_ref.get("plan_type")),
            "network_tier_mapping": _mapping_record(payer_network_tier_index, payer_ref.get("network_tier")),
        }

        payload["reference_data"] = reference_data
        semantics["reference_context"] = reference_semantics

    provenance = provenance_for_source_type(ontology_bundle, event.get("source_type"))
    semantics["provenance"] = provenance
    payload["semantic"] = semantics
    event["provenance"] = provenance
    return event, payload