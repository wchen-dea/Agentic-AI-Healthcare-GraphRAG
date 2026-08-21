from typing import Any

from .models import RequestType


def rank_vector_context(
    items: list[dict[str, Any]],
    request_type: RequestType,
) -> list[dict[str, Any]]:
    event_priority = {
        "medication_safety": {"medication_order": 0, "clinical_note": 1, "claim_status": 2},
        "lab_interpretation": {"lab_result": 0, "vital_sign": 1, "clinical_note": 2},
        "coding_review": {"claim_status": 0, "clinical_note": 1},
        "cohort_triage": {"clinical_note": 0, "lab_result": 1, "vital_sign": 2},
        "patient_summary": {"clinical_note": 0, "lab_result": 1, "medication_order": 2},
    }
    priorities = event_priority.get(request_type, {})

    def _sort_key(item: dict[str, Any]) -> tuple[int, float, str]:
        event_type = str(item.get("event_type") or "")
        priority = priorities.get(event_type, 99)
        score = float(item.get("score") or 0.0)
        event_id = str(item.get("event_id") or "")
        return (priority, -score, event_id)

    return sorted(items, key=_sort_key)


def rank_graph_context(
    items: list[dict[str, Any]],
    request_type: RequestType,
) -> list[dict[str, Any]]:
    if request_type != "cohort_triage":
        return items

    def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
        conditions = len(item.get("conditions") or [])
        observations = len(item.get("observations") or [])
        patient_id = str(item.get("patient_id") or "")
        return (-(conditions + observations), -conditions, patient_id)

    return sorted(items, key=_sort_key)
