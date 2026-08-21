from __future__ import annotations

import hashlib
from typing import Any


def qdrant_point_id(event_id: str) -> int:
    return int(hashlib.md5(event_id.encode("utf-8")).hexdigest()[:16], 16)


def build_qdrant_payload(
    event: dict[str, Any],
    payload: dict[str, Any],
    text: str,
    provenance: dict[str, Any] | None = None,
    *,
    id_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    prov = provenance or {}
    result: dict[str, Any] = {
        "event_id": event["event_id"],
        "event_ts": event["event_ts"],
        "event_type": event["event_type"],
        "event_family": payload.get("event_family"),
        "source_system": event.get("source_system"),
        "source_type": event.get("source_type"),
        "enriched": event.get("enriched", False),
        "reference_hit_count": event.get("reference_hit_count", 0),
        "ontology_version": event.get("ontology_version"),
        "evidence_class": "vector_event_text",
        "trust_level": prov.get("trust_level"),
        "phi_class": prov.get("phi_class"),
        "retention_class": prov.get("retention_class"),
        "text": text,
        "payload": payload,
    }
    # Domain-specific ID fields (patient_id for healthcare, entity_id for supply-chain, etc.)
    for key, event_key in (id_fields or {}).items():
        result[key] = event.get(event_key)
    return result
