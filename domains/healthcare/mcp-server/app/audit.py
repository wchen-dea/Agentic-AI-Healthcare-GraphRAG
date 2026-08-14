from __future__ import annotations

import json
from pathlib import Path


def write_audit_event(audit_log_path: Path, event: dict) -> None:
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")))
        f.write("\n")
