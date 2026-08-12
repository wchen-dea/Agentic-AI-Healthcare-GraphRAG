from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILLS_LAYER_PATH = REPO_ROOT / "rag-api" / "config" / "skills_layer.json"
SKILLS_ROOT = REPO_ROOT / "skills"


def normalize_skill_name(skill_id: str) -> str:
    name = skill_id.strip().lower().replace("_", "-")
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    if not name:
        raise ValueError(f"Unable to derive Agent Skills name from id: {skill_id}")
    return name


def render_skill_md(skill_name: str, skill_id: str, skill: dict, goals: list[str]) -> str:
    description = skill["description"].strip()
    use_when = f"Use when handling workflows related to: {', '.join(goals)}."
    mcp_tools = skill.get("mcp_tools", [])
    runtime_tools = skill.get("runtime_tools", [])
    context_requirements = skill.get("context_requirements", [])
    ontology_dependencies = skill.get("ontology_dependencies", [])

    lines: list[str] = []
    lines.append("---")
    lines.append(f"name: {skill_name}")
    lines.append(f"description: {description} {use_when}")
    lines.append("license: Apache-2.0")
    lines.append("compatibility: Designed for Agent Skills-compatible coding agents with MCP support")
    lines.append("metadata:")
    lines.append(f"  source_skill_id: {skill_id}")
    lines.append("  source_config: rag-api/config/skills_layer.json")
    lines.append("  generator: scripts/generate_agent_skills.py")
    lines.append("---")
    lines.append("")
    lines.append("## Overview")
    lines.append(description)
    lines.append("")
    lines.append("## When To Use")
    lines.append(use_when)
    lines.append("")
    lines.append("## Required Context")
    for item in context_requirements:
        lines.append(f"- {item}")
    if not context_requirements:
        lines.append("- none")
    lines.append("")
    lines.append("## Ontology Dependencies")
    for item in ontology_dependencies:
        lines.append(f"- {item}")
    if not ontology_dependencies:
        lines.append("- none")
    lines.append("")
    lines.append("## MCP Tools")
    for item in mcp_tools:
        lines.append(f"- {item}")
    if not mcp_tools:
        lines.append("- none")
    lines.append("")
    lines.append("## Runtime Tools")
    for item in runtime_tools:
        lines.append(f"- {item}")
    if not runtime_tools:
        lines.append("- none")
    lines.append("")
    lines.append("## Procedure")
    lines.append("1. Validate required context inputs are present.")
    lines.append("2. Resolve ontology prerequisites before tool invocation.")
    lines.append("3. Invoke listed MCP tools in the order that best fits the user request.")
    lines.append("4. Return an evidence-grounded response and capture guardrail metadata.")
    lines.append("")
    lines.append("## References")
    lines.append("See references/REFERENCE.md for source mapping and runtime notes.")
    lines.append("")
    return "\n".join(lines)


def render_reference_md(skill_name: str, skill_id: str, skill: dict, goals: list[str]) -> str:
    lines: list[str] = []
    lines.append(f"# {skill_name}")
    lines.append("")
    lines.append(f"Source skill id: {skill_id}")
    lines.append("")
    lines.append("## Business Goals")
    for goal in goals:
        lines.append(f"- {goal}")
    lines.append("")
    lines.append("## Source Mapping")
    lines.append("- Flow definition: rag-api/config/skills_layer.json")
    lines.append("- Runtime planner: rag-api/skills_layer.py")
    lines.append("- Runtime endpoint: rag-api/app.py (/skills/plan and skills_plan_get)")
    lines.append("")
    lines.append("## Tool and Context Summary")
    lines.append(f"- Context requirements: {', '.join(skill.get('context_requirements', [])) or 'none'}")
    lines.append(f"- Ontology dependencies: {', '.join(skill.get('ontology_dependencies', [])) or 'none'}")
    lines.append(f"- MCP tools: {', '.join(skill.get('mcp_tools', [])) or 'none'}")
    lines.append(f"- Runtime tools: {', '.join(skill.get('runtime_tools', [])) or 'none'}")
    lines.append("")
    return "\n".join(lines)


def generate(check: bool) -> int:
    layer = json.loads(SKILLS_LAYER_PATH.read_text(encoding="utf-8"))
    skills = layer.get("skills", {})
    goals = layer.get("business_goals", {})

    goal_to_skills: dict[str, list[str]] = {
        goal_name: goal.get("skills", []) for goal_name, goal in goals.items()
    }

    SKILLS_ROOT.mkdir(parents=True, exist_ok=True)

    rendered: dict[Path, str] = {}
    generated_dirs: set[str] = set()

    for skill_id, skill in skills.items():
        skill_name = normalize_skill_name(skill_id)
        generated_dirs.add(skill_name)
        skill_dir = SKILLS_ROOT / skill_name
        ref_dir = skill_dir / "references"

        skill_goals = [goal_name for goal_name, skill_ids in goal_to_skills.items() if skill_id in skill_ids]

        rendered[skill_dir / "SKILL.md"] = render_skill_md(skill_name, skill_id, skill, skill_goals)
        rendered[ref_dir / "REFERENCE.md"] = render_reference_md(skill_name, skill_id, skill, skill_goals)

    stale_dirs = [
        path.name
        for path in SKILLS_ROOT.iterdir()
        if path.is_dir() and path.name not in generated_dirs
    ]

    drift = False
    messages: list[str] = []

    for file_path, content in rendered.items():
        exists = file_path.exists()
        current = file_path.read_text(encoding="utf-8") if exists else None
        if current != content:
            drift = True
            messages.append(f"outdated: {file_path.relative_to(REPO_ROOT)}")
            if not check:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")

    if stale_dirs:
        drift = True
        for directory in stale_dirs:
            messages.append(f"stale directory: skills/{directory}")

    if check:
        if drift:
            print("Agent Skills artifacts are out of date:")
            for line in messages:
                print(f"- {line}")
            print("Run: python scripts/generate_agent_skills.py")
            return 1
        print("Agent Skills artifacts are up to date.")
        return 0

    for line in messages:
        print(f"updated: {line}")
    print("Agent Skills scaffold generation complete.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Agent Skills package folders from skills_layer.json")
    parser.add_argument("--check", action="store_true", help="Check whether generated artifacts are up to date")
    args = parser.parse_args()
    return generate(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
