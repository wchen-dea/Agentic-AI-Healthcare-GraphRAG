"""Deterministic role-based tool authorization, enforced before tool execution."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class AuthorizationError(RuntimeError):
    """Raised when a caller role may not invoke a tool."""


@dataclass(frozen=True)
class ToolPolicy:
    """Maps caller roles to the tool names they may invoke. Unknown roles get nothing."""

    roles: dict[str, frozenset[str]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolPolicy:
        raw_roles = data.get("roles", {}) or {}
        return cls(roles={role: frozenset(tools or []) for role, tools in raw_roles.items()})

    @classmethod
    def load(cls, path: str | Path) -> ToolPolicy:
        """Load a JSON policy file. A missing file yields a deny-all policy."""
        policy_path = Path(path)
        if not policy_path.exists():
            return cls(roles={})
        with policy_path.open("r", encoding="utf-8") as handle:
            return cls.from_dict(json.load(handle))

    def allowed_tools(self, caller_role: str) -> frozenset[str]:
        return self.roles.get(caller_role, frozenset())

    def authorize(self, *, tool_name: str, caller_role: str) -> str:
        """Return the caller id for audit, or raise ``AuthorizationError``."""
        if tool_name not in self.allowed_tools(caller_role):
            raise AuthorizationError(f"Role '{caller_role}' is not authorized for tool '{tool_name}'")
        return f"role:{caller_role}"
