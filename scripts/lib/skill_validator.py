"""Validate Agent Skills packages against skills_layer.json."""
from __future__ import annotations

import json
import re
from pathlib import Path

NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def normalize_skill_name(skill_id: str) -> str:
    name = skill_id.strip().lower().replace("_", "-")
    name = re.sub(r"[^a-z0-9-]", "-", name)
    name = re.sub(r"-+", "-", name).strip("-")
    return name


def parse_frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing YAML frontmatter start")

    try:
        _, remainder = text.split("---\n", 1)
        fm_text, body = remainder.split("\n---\n", 1)
    except ValueError as exc:
        raise ValueError(f"{path}: invalid frontmatter delimiters") from exc

    if not body.strip():
        raise ValueError(f"{path}: Markdown body is empty")

    frontmatter: dict[str, object] = {}
    metadata: dict[str, str] = {}
    in_metadata = False

    for raw_line in fm_text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if in_metadata:
            if raw_line.startswith("  ") and ":" in raw_line:
                key, value = raw_line.strip().split(":", 1)
                metadata[key.strip()] = value.strip()
                continue
            in_metadata = False

        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if key == "metadata":
            in_metadata = True
            frontmatter[key] = metadata
            continue

        frontmatter[key] = value

    return frontmatter


def _validate_skill(
    skill_dir: Path, expected_name: str, domain_root: Path, errors: list[str],
) -> None:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append(f"Missing SKILL.md: {skill_md.relative_to(domain_root)}")
        return

    try:
        fm = parse_frontmatter(skill_md)
    except ValueError as exc:
        errors.append(str(exc))
        return

    name = str(fm.get("name", ""))
    description = str(fm.get("description", ""))

    if not name:
        errors.append(f"{skill_md.relative_to(domain_root)}: missing required field 'name'")
    elif len(name) > 64:
        errors.append(f"{skill_md.relative_to(domain_root)}: name exceeds 64 characters")
    elif not NAME_PATTERN.fullmatch(name):
        errors.append(f"{skill_md.relative_to(domain_root)}: name must match ^[a-z0-9]+(?:-[a-z0-9]+)*$")

    if name and name != expected_name:
        errors.append(
            f"{skill_md.relative_to(domain_root)}: name '{name}' must match parent directory '{expected_name}'"
        )

    if not description:
        errors.append(f"{skill_md.relative_to(domain_root)}: missing required field 'description'")
    elif len(description) > 1024:
        errors.append(f"{skill_md.relative_to(domain_root)}: description exceeds 1024 characters")


def validate_skills(
    skills_layer_path: Path,
    skills_root: Path,
    domain_root: Path,
) -> int:
    """Validate skill packages. Returns 0 on success, 1 on failure."""
    if not skills_layer_path.exists():
        print(f"Missing skills layer config: {skills_layer_path.relative_to(domain_root)}")
        return 1

    if not skills_root.exists():
        print(f"Missing skills directory: {skills_root.relative_to(domain_root)}")
        return 1

    layer = json.loads(skills_layer_path.read_text(encoding="utf-8"))
    skills = layer.get("skills", {})
    expected_dirs = {normalize_skill_name(skill_id) for skill_id in skills.keys()}

    errors: list[str] = []

    for expected in sorted(expected_dirs):
        _validate_skill(skills_root / expected, expected, domain_root, errors)

    extra_dirs = [
        path.name
        for path in skills_root.iterdir()
        if path.is_dir() and path.name not in expected_dirs
    ]
    for extra in sorted(extra_dirs):
        errors.append(f"Unexpected skills directory not defined in skills_layer.json: skills/{extra}")

    if errors:
        print("Agent Skills validation failed:")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Agent Skills validation passed.")
    return 0
