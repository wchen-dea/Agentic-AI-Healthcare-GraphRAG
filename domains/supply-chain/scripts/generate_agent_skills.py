from __future__ import annotations

import argparse
import sys
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOMAIN_ROOT.parents[1] / "scripts"))

from lib.skill_generator import generate_skills  # noqa: E402

SKILLS_LAYER_PATH = DOMAIN_ROOT / "agent-service" / "src" / "supply_chain_agent" / "config" / "skills_layer.json"
SKILLS_ROOT = DOMAIN_ROOT / "knowledge" / "skills"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Agent Skills package folders from skills_layer.json")
    parser.add_argument("--check", action="store_true", help="Check whether generated artifacts are up to date")
    args = parser.parse_args()
    return generate_skills(
        skills_layer_path=SKILLS_LAYER_PATH,
        skills_root=SKILLS_ROOT,
        domain_root=DOMAIN_ROOT,
        check=args.check,
        source_config_path="agent-service/src/supply_chain_agent/config/skills_layer.json",
        planner_path="agent-service/src/supply_chain_agent/tools/skills.py",
        endpoint_path="agent-service/src/supply_chain_agent/api/routes.py (/skills/plan) and tools/mcp_server.py (skills_plan_get)",
    )


if __name__ == "__main__":
    raise SystemExit(main())
