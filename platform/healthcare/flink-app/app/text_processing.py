from __future__ import annotations

import hashlib
import json
import os


VECTOR_SIZE = 384
_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model
    try:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(_EMBEDDING_MODEL_NAME)
        print(f"Loaded neural embedding model: {_EMBEDDING_MODEL_NAME}")
    except Exception:
        _embedding_model = False
        print("sentence-transformers not available, using deterministic MD5 embedding")
    return _embedding_model


def _md5_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    vec = [0.0] * dim
    for token in text.lower().split():
        token_hash = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        vec[token_hash % dim] += 1.0
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm if norm else 0.0 for x in vec]


def stable_embedding(text: str, dim: int = VECTOR_SIZE) -> list[float]:
    model = _get_embedding_model()
    if model and model is not False:
        vec = model.encode(text, normalize_embeddings=True).tolist()
        return vec[:dim] if len(vec) >= dim else vec + [0.0] * (dim - len(vec))
    return _md5_embedding(text, dim)


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