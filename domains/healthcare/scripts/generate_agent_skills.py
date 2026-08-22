from __future__ import annotations

import argparse
import sys
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOMAIN_ROOT.parents[1] / "scripts"))

from lib.skill_generator import generate_skills  # noqa: E402

SKILLS_LAYER_PATH = DOMAIN_ROOT / "agents" / "config" / "skills_layer.json"
SKILLS_ROOT = DOMAIN_ROOT / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Agent Skills package folders from skills_layer.json")
    parser.add_argument("--check", action="store_true", help="Check whether generated artifacts are up to date")
    args = parser.parse_args()
    return generate_skills(
        skills_layer_path=SKILLS_LAYER_PATH,
        skills_root=SKILLS_ROOT,
        domain_root=DOMAIN_ROOT,
        check=args.check,
        source_config_path="rag-api/config/skills_layer.json",
        planner_path="rag-api/skills_layer.py",
        endpoint_path="rag-api/app.py (/skills/plan and skills_plan_get)",
    )


if __name__ == "__main__":
    raise SystemExit(main())
