from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


class AuthorizationError(RuntimeError):
    pass


@lru_cache(maxsize=4)
def load_policy(path: str) -> dict:
    policy_path = Path(path)
    if not policy_path.exists():
        return {"roles": {}}
    with policy_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def authorize(
    *,
    tool_name: str,
    caller_role: str,
    auth_token: str | None,
    require_auth: bool,
    expected_token: str,
    policy_path: str,
) -> str:
    if require_auth:
        if not expected_token:
            raise AuthorizationError("MCP auth is enabled but MCP_API_TOKEN is empty")
        if auth_token != expected_token:
            raise AuthorizationError("Invalid auth token")

    policy = load_policy(policy_path)
    allowed_tools = set(policy.get("roles", {}).get(caller_role, []))
    if tool_name not in allowed_tools:
        raise AuthorizationError(
            f"Role '{caller_role}' is not authorized for tool '{tool_name}'"
        )

    if require_auth:
        return f"token:{caller_role}"
    return f"local:{caller_role}"
