"""Shared FastMCP server factory for agent services.

Requires the ``mcp`` extra (``agent-core[mcp]``). Domain services describe
their tools with ``ToolSpec`` and use these helpers so every MCP surface gets
the same transport security, tool metadata, non-blocking execution, and
skills-layer resources and prompts.

Governance stays in the domain tool methods (``ToolGovernance.execute``); this
module only shapes how those methods are exposed over MCP.
"""
from __future__ import annotations

import functools
import inspect
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

import anyio.to_thread
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from agent_core.settings import AgentServiceSettings

ToolKind = Literal["read_only", "generation", "export", "memory_write"]

# MCP annotations are client hints, not enforcement: role policy is still
# applied by ToolGovernance before any tool body runs. Patient-memory writes
# are explicitly marked as mutating and idempotent because fact IDs or keys
# provide upsert semantics.
_ANNOTATIONS: dict[ToolKind, dict[str, bool]] = {
    "read_only": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False},
    "generation": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
    "export": {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": False, "openWorldHint": False},
    "memory_write": {"readOnlyHint": True, "destructiveHint": True, "idempotentHint": True, "openWorldHint": False},
}

SKILLS_CATALOG_URI = "skills://catalog"
SKILL_URI_TEMPLATE = "skills://{skill_id}"


@dataclass(frozen=True)
class ToolSpec:
    """MCP metadata for one governed tool method."""

    name: str
    title: str
    kind: ToolKind
    description: str = ""


def tool_annotations(spec: ToolSpec) -> ToolAnnotations:
    return ToolAnnotations(title=spec.title, **_ANNOTATIONS[spec.kind])


def transport_security(settings: AgentServiceSettings) -> TransportSecuritySettings:
    # Always explicit: FastMCP otherwise auto-enables DNS-rebinding protection
    # for localhost binds, which rejects Docker service-name Host headers.
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=settings.mcp_dns_rebinding_protection,
        allowed_hosts=list(settings.mcp_allowed_hosts),
        allowed_origins=list(settings.mcp_allowed_origins),
    )


def build_mcp_server(settings: AgentServiceSettings, *, name: str, instructions: str = "") -> FastMCP:
    """Create a FastMCP server configured from service settings."""
    return FastMCP(
        name,
        instructions=settings.mcp_instructions or instructions or None,
        stateless_http=settings.mcp_stateless_http,
        json_response=settings.mcp_json_response,
        transport_security=transport_security(settings),
    )


def offload_to_thread(fn: Callable[..., Any]) -> Callable[..., Any]:
    """Wrap a blocking callable as a coroutine that runs in a worker thread.

    The wrapper keeps the original signature, evaluated annotations, name, and
    docstring so FastMCP derives the same argument schema.
    """
    signature = inspect.signature(fn, eval_str=True)

    async def _run(**kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(functools.partial(fn, **kwargs))

    _run.__name__ = getattr(fn, "__name__", "tool")
    _run.__qualname__ = getattr(fn, "__qualname__", _run.__name__)
    _run.__doc__ = fn.__doc__
    _run.__signature__ = signature  # type: ignore[attr-defined]
    annotations = {name: p.annotation for name, p in signature.parameters.items() if p.annotation is not p.empty}
    if signature.return_annotation is not signature.empty:
        annotations["return"] = signature.return_annotation
    _run.__annotations__ = annotations
    return _run


def register_tools(mcp: FastMCP, target: object, specs: Iterable[ToolSpec], *, offload: bool = True) -> None:
    """Register ``target.<spec.name>`` methods as MCP tools with metadata."""
    for spec in specs:
        method = getattr(target, spec.name)
        description = spec.description or inspect.getdoc(method) or None
        mcp.tool(
            name=spec.name,
            title=spec.title,
            description=description,
            annotations=tool_annotations(spec),
        )(offload_to_thread(method) if offload else method)


def _skill_summary(skill_id: str, skill: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": skill_id,
        "description": skill.get("description", ""),
        "mcp_tools": list(skill.get("mcp_tools", [])),
        "uri": f"skills://{skill_id}",
    }


def skills_catalog(layer: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": layer.get("version"),
        "flow": layer.get("flow", []),
        "business_goals": {
            goal_id: {
                "description": goal.get("description", ""),
                "default_agent": goal.get("default_agent", ""),
                "skills": list(goal.get("skills", [])),
            }
            for goal_id, goal in layer.get("business_goals", {}).items()
        },
        "skills": [_skill_summary(skill_id, skill) for skill_id, skill in layer.get("skills", {}).items()],
    }


def render_review_prompt(
    layer: dict[str, Any],
    *,
    business_goal: str,
    subject_label: str,
    subject_id: str = "",
) -> str:
    goals = layer.get("business_goals", {})
    goal = goals.get(business_goal)
    if goal is None:
        raise ValueError(f"Unknown business_goal '{business_goal}'. Known goals: {', '.join(sorted(goals))}")
    skills = layer.get("skills", {})
    lines = [
        f"Business goal: {business_goal} - {goal.get('description', '')}",
        f"Agent: {goal.get('default_agent', '')}",
    ]
    if subject_id:
        lines.append(f"{subject_label}: {subject_id}")
    lines.append("Run these skills in order and call only the listed MCP tools:")
    for skill_id in goal.get("skills", []):
        skill = skills.get(skill_id, {})
        tools = ", ".join(skill.get("mcp_tools", [])) or "none"
        lines.append(f"- {skill_id}: {skill.get('description', '')} (tools: {tools})")
    lines.append(
        "Ground every statement in tool output, cite the evidence ids returned by the tools, "
        "and say so explicitly when evidence is missing instead of guessing."
    )
    return "\n".join(lines)


def register_skills_surface(
    mcp: FastMCP,
    load_layer: Callable[[], dict[str, Any]],
    *,
    prompt_name: str,
    prompt_title: str,
    subject_label: str,
) -> None:
    """Expose the skills layer as MCP resources plus one review prompt.

    ``load_layer`` is called per request so resource reads reflect the
    configured skills file without restarting the server.
    """

    @mcp.resource(
        SKILLS_CATALOG_URI,
        name="skills_catalog",
        title="Skills catalog",
        description="Business goals, agents, and skills with the MCP tools each skill uses.",
        mime_type="application/json",
    )
    def _catalog() -> str:
        return json.dumps(skills_catalog(load_layer()), sort_keys=True)

    @mcp.resource(
        SKILL_URI_TEMPLATE,
        name="skill",
        title="Skill definition",
        description="One skill: context requirements, ontology dependencies, MCP and runtime tools.",
        mime_type="application/json",
    )
    def _skill(skill_id: str) -> str:
        skills = load_layer().get("skills", {})
        if skill_id not in skills:
            raise ValueError(f"Unknown skill '{skill_id}'")
        return json.dumps({"id": skill_id, **skills[skill_id]}, sort_keys=True)

    @mcp.prompt(
        name=prompt_name,
        title=prompt_title,
        description=f"Plan a governed review for a business goal; optionally scope it to one {subject_label.lower()}.",
    )
    def _prompt(business_goal: str, subject_id: str = "") -> str:
        return render_review_prompt(
            load_layer(),
            business_goal=business_goal,
            subject_label=subject_label,
            subject_id=subject_id,
        )
