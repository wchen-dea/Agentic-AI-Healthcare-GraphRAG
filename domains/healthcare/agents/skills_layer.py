from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class SkillsLayerError(ValueError):
    pass


def load_skills_layer(path: str) -> dict[str, Any]:
    skills_path = Path(path)
    if not skills_path.exists():
        raise SkillsLayerError(f"Skills layer config not found: {skills_path}")

    with skills_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    _validate_layer(payload)
    return payload


def build_skill_plan(
    layer: dict[str, Any],
    *,
    business_goal: str,
    agent: str | None = None,
) -> dict[str, Any]:
    goals = layer.get("business_goals", {})
    skills_registry = layer.get("skills", {})

    goal_entry = goals.get(business_goal)
    if goal_entry is None:
        available = sorted(goals.keys())
        raise SkillsLayerError(
            f"Unknown business_goal '{business_goal}'. Available goals: {available}"
        )

    selected_agent = agent or goal_entry.get("default_agent") or "default_agent"
    skill_ids = goal_entry.get("skills", [])

    resolved_skills: list[dict[str, Any]] = []
    mcp_tools: list[str] = []
    runtime_tools: list[str] = []
    ontology_dependencies: list[str] = []

    for skill_id in skill_ids:
        skill = skills_registry.get(skill_id)
        if skill is None:
            raise SkillsLayerError(
                f"business_goal '{business_goal}' references unknown skill '{skill_id}'"
            )
        resolved_skills.append({"id": skill_id, **skill})
        mcp_tools.extend(skill.get("mcp_tools", []))
        runtime_tools.extend(skill.get("runtime_tools", []))
        ontology_dependencies.extend(skill.get("ontology_dependencies", []))

    return {
        "version": layer.get("version", "unknown"),
        "flow": layer.get("flow", []),
        "business_goal": business_goal,
        "goal_description": goal_entry.get("description", ""),
        "agent": selected_agent,
        "skills": resolved_skills,
        "context_requirements": _unique(
            req
            for skill in resolved_skills
            for req in skill.get("context_requirements", [])
        ),
        "ontology_dependencies": _unique(ontology_dependencies),
        "mcp_tools": _unique(mcp_tools),
        "runtime_tools": _unique(runtime_tools),
    }


def _validate_layer(layer: dict[str, Any]) -> None:
    if not isinstance(layer, dict):
        raise SkillsLayerError("Skills layer config must be a JSON object")

    if "business_goals" not in layer or "skills" not in layer:
        raise SkillsLayerError("Skills layer config must contain 'business_goals' and 'skills'")

    if not isinstance(layer.get("business_goals"), dict):
        raise SkillsLayerError("'business_goals' must be an object")

    if not isinstance(layer.get("skills"), dict):
        raise SkillsLayerError("'skills' must be an object")


def _unique(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result
