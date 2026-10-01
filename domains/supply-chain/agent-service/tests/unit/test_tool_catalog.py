"""Guard against drift between the skills layer, tool policy and MCP tools."""
from __future__ import annotations

import json
from importlib import resources

from supply_chain_agent.tools.mcp_server import TOOL_NAMES


def _config(name: str) -> dict:
    return json.loads(resources.files("supply_chain_agent.config").joinpath(name).read_text(encoding="utf-8"))


def test_skills_reference_only_implemented_mcp_tools() -> None:
    skills = _config("skills_layer.json")["skills"]
    referenced = {tool for skill in skills.values() for tool in skill.get("mcp_tools", [])}
    assert referenced - set(TOOL_NAMES) == set()


def test_every_mcp_tool_is_granted_by_some_role() -> None:
    policies = _config("tool_policies.json")
    granted = {tool for tools in policies["roles"].values() for tool in tools}
    assert set(TOOL_NAMES) - granted == set()
