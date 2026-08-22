from __future__ import annotations


def update_reference_store(reference_store: dict, topic: str, event: dict, payload: dict) -> None:
    if topic == "healthcare.master.patients":
        patient_id = payload.get("patient_id") or event.get("patient_id")
        if patient_id:
            reference_store["patients"][patient_id] = payload
        return

    if topic == "healthcare.master.providers":
        provider_id = payload.get("provider_id") or event.get("provider_id")
        if provider_id:
            reference_store["providers"][provider_id] = payload
        return

    if topic == "healthcare.master.devices":
        device_id = payload.get("device_id")
        if device_id:
            reference_store["devices"][device_id] = payload
        return

    if topic == "healthcare.master.medications":
        medication = payload.get("medication")
        if medication:
            reference_store["medications"][medication] = payload
        return

    if topic == "healthcare.master.payers":
        payer = payload.get("payer")
        if payer:
            reference_store["payers"][payer] = payload


def build_reference_data(reference_store: dict, event: dict, payload: dict) -> dict:
    patient_id = event.get("patient_id")
    provider_id = event.get("provider_id")
    device_id = payload.get("device_id")
    medication = payload.get("medication")
    payer = payload.get("payer")

    return {
        "patient": reference_store["patients"].get(patient_id),
        "provider": reference_store["providers"].get(provider_id),
        "device": reference_store["devices"].get(device_id),
        "medication": reference_store["medications"].get(medication),
        "payer": reference_store["payers"].get(payer),
    }