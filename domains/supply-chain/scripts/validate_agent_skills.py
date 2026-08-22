from __future__ import annotations

import sys
from pathlib import Path

DOMAIN_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DOMAIN_ROOT.parents[1] / "scripts"))

from lib.skill_validator import validate_skills  # noqa: E402

SKILLS_LAYER_PATH = DOMAIN_ROOT / "agents" / "config" / "skills_layer.json"
SKILLS_ROOT = DOMAIN_ROOT / "skills"


def main() -> int:
    return validate_skills(SKILLS_LAYER_PATH, SKILLS_ROOT, DOMAIN_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
