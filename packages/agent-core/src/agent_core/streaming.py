"""Server-sent event (SSE) contract for streamed agent runs.

A stream is ``meta``, zero or more ``step`` events, then exactly one terminal
``result`` or ``error`` event. Clients (the webapp) depend on these names.
"""
from __future__ import annotations

import json
from typing import Any, Final, Literal

StreamEventType = Literal["meta", "step", "result", "error"]
TERMINAL_EVENTS: Final[frozenset[str]] = frozenset({"result", "error"})
SSE_HEADERS: Final[dict[str, str]] = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def format_sse(event: StreamEventType, data: dict[str, Any] | str, event_id: int) -> str:
    """Encode one SSE frame. ``data`` that is already a JSON string is sent as-is."""
    body = data if isinstance(data, str) else json.dumps(data, separators=(",", ":"))
    return f"id: {event_id}\nevent: {event}\ndata: {body}\n\n"
