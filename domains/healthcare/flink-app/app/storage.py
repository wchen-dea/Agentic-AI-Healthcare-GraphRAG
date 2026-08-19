from __future__ import annotations

import hashlib
from typing import Any


def qdrant_point_id(event_id: str) -> int:
    return int(hashlib.md5(event_id.encode("utf-8")).hexdigest()[:16], 16)


def build_qdrant_payload(
    event: dict[str, Any],
    payload: dict[str, Any],
    text: str,
    provenance: dict[str, Any],
) -> dict[str, Any]:
    return {
        "event_id": event["event_id"],
        "event_ts": event["event_ts"],
        "event_type": event["event_type"],
        "event_family": payload.get("event_family"),
        "patient_id": event.get("patient_id"),
        "source_system": event.get("source_system"),
        "source_type": event.get("source_type"),
        "enriched": event.get("enriched", False),
        "reference_hit_count": event.get("reference_hit_count", 0),
        "ontology_version": event.get("ontology_version"),
        "evidence_class": "vector_event_text",
        "trust_level": provenance.get("trust_level"),
        "phi_class": provenance.get("phi_class"),
        "retention_class": provenance.get("retention_class"),
        "text": text,
        "payload": payload,
    }