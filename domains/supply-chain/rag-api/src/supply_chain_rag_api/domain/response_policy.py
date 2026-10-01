"""Response sanitization, truncation, and budget enforcement.

Extracted from app.py to isolate output policy logic from HTTP/MCP handlers.
"""
from __future__ import annotations

import json
from typing import Any


def truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    if max_chars <= 3:
        return value[:max_chars]
    return value[: max_chars - 3] + "..."


def graph_limits(caller_role: str, *, max_evidence_chars: int, max_context_items: int) -> tuple[int, int]:
    if caller_role == "export":
        return max_evidence_chars * 2, max_context_items * 2
    return max_evidence_chars, max_context_items


def sanitize_graph_value(value: Any, *, text_limit: int, list_limit: int) -> Any:
    if isinstance(value, str):
        return truncate_text(value, text_limit)
    if isinstance(value, list):
        return [
            sanitize_graph_value(item, text_limit=text_limit, list_limit=list_limit)
            for item in value[:list_limit]
        ]
    if isinstance(value, dict):
        return {
            key: sanitize_graph_value(item, text_limit=text_limit, list_limit=list_limit)
            for key, item in value.items()
        }
    return value


def vector_text_mode(caller_role: str, include_raw_payload: bool = False) -> str:
    if caller_role == "export":
        return "bounded"
    if include_raw_payload:
        return "request-denied"
    return "none"


def sanitize_vector_context_for_role(
    items: list[dict[str, Any]],
    *,
    caller_role: str,
    include_raw_payload: bool = False,
    max_context_items: int = 5,
    max_evidence_chars: int = 240,
) -> list[dict[str, Any]]:
    text_mode = vector_text_mode(caller_role, include_raw_payload=include_raw_payload)
    sanitized: list[dict[str, Any]] = []
    for item in items[:max_context_items]:
        safe_item = {
            "score": item.get("score"),
            "event_id": item.get("event_id"),
            "patient_id": item.get("patient_id"),
            "event_type": item.get("event_type"),
        }
        text = item.get("text")
        if text_mode == "bounded" and text:
            safe_item["text"] = truncate_text(str(text), max_evidence_chars)
        elif text:
            safe_item["text_redacted"] = True
        sanitized.append(safe_item)
    return sanitized


def sanitize_graph_context_for_role(
    items: list[dict[str, Any]],
    *,
    caller_role: str,
    max_evidence_chars: int = 240,
    max_context_items: int = 5,
) -> list[dict[str, Any]]:
    text_limit, list_limit = graph_limits(
        caller_role,
        max_evidence_chars=max_evidence_chars,
        max_context_items=max_context_items,
    )
    return [
        sanitize_graph_value(item, text_limit=text_limit, list_limit=list_limit)
        for item in items[:list_limit]
    ]


def apply_response_budget(
    payload: dict[str, Any], *, max_response_bytes: int = 50000,
) -> dict[str, Any]:
    payload.setdefault("guardrails", {})
    payload["guardrails"].setdefault("response_truncated", False)

    while len(json.dumps(payload, separators=(",", ":")).encode("utf-8")) > max_response_bytes:
        payload["guardrails"]["response_truncated"] = True
        vector_items = payload.get("vector_context") or []
        if vector_items:
            vector_items.pop()
            continue

        graph_items = payload.get("graph_context") or []
        if graph_items:
            graph_items.pop()
            continue

        answer = payload.get("answer")
        if isinstance(answer, str) and len(answer) > 80:
            payload["answer"] = truncate_text(answer, max(80, len(answer) - 80))
            continue

        break

    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    if len(encoded) > max_response_bytes:
        raise RuntimeError("Unable to fit response within configured response budget")
    return payload


def estimate_confidence(
    vector_items: list[dict[str, Any]],
    graph_items: list[dict[str, Any]],
) -> float:
    if vector_items and graph_items:
        return 1.0
    if vector_items or graph_items:
        return 0.5
    return 0.0
