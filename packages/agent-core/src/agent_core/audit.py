"""Audit events for tool and query execution.

Events record a hash of the request, never the raw payload, so sensitive input
does not reach the audit log. ``scope`` names the data subjects a call touched
(patient ids, supplier ids, ``"cohort"``); each sink chooses the JSON key, so a
domain keeps its existing audit schema (healthcare writes ``patient_scope``).
"""
from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


def hash_payload(payload: dict[str, Any]) -> str:
    """Stable SHA-256 of a JSON-serializable payload."""
    data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AuditEvent:
    trace_id: str
    tool_name: str
    caller_id: str
    input_hash: str
    scope: list[str] | str
    outcome: str
    latency_ms: int
    response_size_bytes: int
    error: str | None = None
    timestamp: str = field(default_factory=utc_timestamp)

    def to_dict(self, scope_key: str = "scope") -> dict[str, Any]:
        event = asdict(self)
        if scope_key != "scope":
            event = {(scope_key if key == "scope" else key): value for key, value in event.items()}
        if not event["error"]:
            del event["error"]
        return event


class AuditSink(Protocol):
    def write(self, event: AuditEvent) -> bool: ...


AuditFailureHandler = Callable[[AuditEvent, Exception], None]


class JsonlAuditSink:
    """Appends one JSON object per line. Write failures are reported to callers.

    Requests must not crash because the audit volume is unavailable, but the
    failure must be visible: ``on_failure`` should emit a metric and an error log.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        on_failure: AuditFailureHandler | None = None,
        scope_key: str = "scope",
    ) -> None:
        self.path = Path(path)
        self._on_failure = on_failure
        self._scope_key = scope_key
        self._lock = threading.Lock()

    def write(self, event: AuditEvent) -> bool:
        line = json.dumps(event.to_dict(self._scope_key), separators=(",", ":"))
        try:
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.write("\n")
            return True
        except OSError as exc:
            if self._on_failure is not None:
                self._on_failure(event, exc)
            return False
