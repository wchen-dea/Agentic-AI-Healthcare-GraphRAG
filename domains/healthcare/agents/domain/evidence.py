from typing import Any

import time

from .models import RequestType


_RECENCY_WEIGHT = 0.3
_RELEVANCE_WEIGHT = 0.5
_GRAPH_SIGNAL_WEIGHT = 0.2


def _recency_score(item: dict[str, Any], now: float | None = None) -> float:
    """Score 0-1 based on event recency (24h window)."""
    event_ts = item.get("event_ts") or item.get("timestamp")
    if not event_ts:
        return 0.5
    try:
        from datetime import datetime, timezone
        if isinstance(event_ts, str):
            ts = datetime.fromisoformat(event_ts.replace("Z", "+00:00")).timestamp()
        else:
            ts = float(event_ts)
        age_hours = ((now or time.time()) - ts) / 3600
        return max(0.0, min(1.0, 1.0 - (age_hours / 24.0)))
    except (ValueError, TypeError):
        return 0.5


def _graph_signal_score(item: dict[str, Any], graph_patient_ids: set[str] | None = None) -> float:
    """Score 0-1 based on whether the event's patient has graph context."""
    if not graph_patient_ids:
        return 0.5
    patient_id = item.get("patient_id")
    return 1.0 if patient_id in graph_patient_ids else 0.0


def fusion_rerank(
    items: list[dict[str, Any]],
    graph_patient_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Cross-source reranking combining relevance, recency, and graph signal."""
    now = time.time()
    scored = []
    for item in items:
        relevance = float(item.get("score") or 0.0)
        recency = _recency_score(item, now)
        graph_sig = _graph_signal_score(item, graph_patient_ids)
        fusion = (
            _RELEVANCE_WEIGHT * relevance
            + _RECENCY_WEIGHT * recency
            + _GRAPH_SIGNAL_WEIGHT * graph_sig
        )
        scored.append((fusion, item))
    scored.sort(key=lambda x: (-x[0], str(x[1].get("event_id", ""))))
    return [item for _, item in scored]


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
