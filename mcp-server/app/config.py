from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    server_name: str
    require_auth: bool
    api_token: str
    tool_policy_path: Path
    audit_log_path: Path
    rag_api_base_url: str
    rag_api_timeout_seconds: int


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root = Path(__file__).resolve().parents[1]

    tool_policy_path = Path(
        os.getenv("MCP_TOOL_POLICY_PATH", str(root / "config" / "tool_policies.json"))
    )
    if not tool_policy_path.is_absolute():
        tool_policy_path = root / tool_policy_path

    audit_log_path = Path(
        os.getenv("MCP_AUDIT_LOG_PATH", str(root / "logs" / "mcp_audit.log"))
    )
    if not audit_log_path.is_absolute():
        audit_log_path = root / audit_log_path

    return Settings(
        server_name=os.getenv("MCP_SERVER_NAME", "HealthcareGraphRAG MCP"),
        require_auth=_to_bool(os.getenv("MCP_REQUIRE_AUTH", "false")),
        api_token=os.getenv("MCP_API_TOKEN", ""),
        tool_policy_path=tool_policy_path,
        audit_log_path=audit_log_path,
        rag_api_base_url=os.getenv("RAG_API_BASE_URL", "http://localhost:8000"),
        rag_api_timeout_seconds=int(os.getenv("RAG_API_TIMEOUT_SECONDS", "30")),
    )
