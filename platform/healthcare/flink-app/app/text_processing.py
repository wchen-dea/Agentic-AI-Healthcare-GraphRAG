from __future__ import annotations

import json
import os
import sys

# Make shared embedding module importable (local dev and container paths)
_shared_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "shared")
_container_shared = os.path.join(os.path.dirname(__file__), "..", "shared")
for _candidate in [_shared_dir, _container_shared]:
    _parent = os.path.dirname(_candidate)
    if os.path.isdir(_candidate) and _parent not in sys.path:
        sys.path.insert(0, _parent)

from shared.embedding import (  # noqa: E402
    ALL_DOMAINS,
    VECTOR_SIZE,
    EmbeddingDomain,
    domain_for_event_type,
    stable_embedding,
)


def clinical_text(event: dict) -> str:
    payload = json.loads(event.get("payload_json", "{}"))
    event_type = event.get("event_type")
    reference = payload.get("reference_data", {})

    ref_parts = []
    patient_ref = reference.get("patient")
    provider_ref = reference.get("provider")
    device_ref = reference.get("device")
    medication_ref = reference.get("medication")
    payer_ref = reference.get("payer")

    if patient_ref:
        ref_parts.append(
            f"Patient profile age {patient_ref.get('age')}, sex {patient_ref.get('sex')}, risk {patient_ref.get('risk_tier')}."
        )
    if provider_ref:
        ref_parts.append(
            f"Provider {provider_ref.get('name')} specialty {provider_ref.get('specialty')}."
        )
    if device_ref:
        ref_parts.append(
            f"Device model {device_ref.get('model')} vendor {device_ref.get('vendor')}."
        )
    if medication_ref:
        ref_parts.append(
            f"Medication class {medication_ref.get('drug_class')} safety tier {medication_ref.get('safety_tier')}."
        )
    if payer_ref:
        ref_parts.append(
            f"Payer plan {payer_ref.get('plan_type')} region {payer_ref.get('region')}."
        )

    ref_summary = " ".join([part for part in ref_parts if part and "None" not in part])

    if event_type == "CLINICAL_NOTE":
        return " ".join(
            [
                item
                for item in [
                    f"Patient {event['patient_id']} clinical note from {event['source_system']}. "
                    f"Diagnosis {payload.get('diagnosis')} ICD10 {payload.get('icd10_code')}. "
                    f"Symptom {payload.get('symptom')}. Note: {payload.get('note')}",
                    ref_summary,
                ]
                if item
            ]
        )
    if event_type == "LAB_RESULT":
        return " ".join(
            [
                item
                for item in [
                    f"Patient {event['patient_id']} lab result. "
                    f"{payload.get('lab_name')} equals {payload.get('value')} {payload.get('unit')}. "
                    f"Panel {payload.get('lab_panel')}. Specimen {payload.get('specimen_type')}. "
                    f"Abnormal: {payload.get('abnormal')}",
                    ref_summary,
                ]
                if item
            ]
        )
    if event_type == "VITAL_SIGN":
        parts = [
            f"Patient {event['patient_id']} device telemetry from {event['source_system']}. "
            f"Heart rate {payload.get('heart_rate')}, SpO2 {payload.get('spo2')}, "
            f"BP {payload.get('systolic_bp')}/{payload.get('diastolic_bp')}, "
            f"temp {payload.get('temperature_c')} C, RR {payload.get('respiratory_rate')}.",
        ]
        if payload.get("alert"):
            parts.append(f"Alert: {payload.get('alert')}.")
        if ref_summary:
            parts.append(ref_summary)
        return " ".join(parts)
    if event_type == "MEDICATION_ORDER":
        return " ".join(
            [
                item
                for item in [
                    f"Patient {event['patient_id']} medication order. "
                    f"Medication {payload.get('medication')} drug class {payload.get('drug_class')} "
                    f"dose {payload.get('dose')} route {payload.get('route')} "
                    f"frequency {payload.get('frequency')} order type {payload.get('order_type')}.",
                    ref_summary,
                ]
                if item
            ]
        )
    if event_type == "CLAIM_STATUS":
        return " ".join(
            [
                item
                for item in [
                    f"Patient {event['patient_id']} claim event. "
                    f"Payer {payload.get('payer')} procedure {payload.get('procedure_code')} "
                    f"{payload.get('procedure_description')} diagnosis {payload.get('diagnosis_code')} "
                    f"billed {payload.get('billed_amount')} status {payload.get('status')}.",
                    ref_summary,
                ]
                if item
            ]
        )
    return json.dumps(event)