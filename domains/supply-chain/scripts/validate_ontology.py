#!/usr/bin/env python3
"""Validate supply-chain ontology YAML files load without errors."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PLATFORM_DIR = Path(__file__).resolve().parents[3] / "data-platform" / "supply-chain"
CONFIG_DIR = DATA_PLATFORM_DIR / "config" / "ontology"

try:
    import yaml
except ImportError:
    print("PyYAML not installed; skipping ontology validation.")
    sys.exit(0)


def validate():
    errors = 0
    for path in sorted(CONFIG_DIR.rglob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data is None:
                print(f"WARN: empty file {path.relative_to(DATA_PLATFORM_DIR)}")
            elif not isinstance(data, dict):
                print(f"FAIL: {path.relative_to(DATA_PLATFORM_DIR)} is not a mapping")
                errors += 1
            else:
                print(f"OK:   {path.relative_to(DATA_PLATFORM_DIR)}")
        except Exception as ex:
            print(f"FAIL: {path.relative_to(DATA_PLATFORM_DIR)}: {ex}")
            errors += 1

    if errors:
        print(f"\n{errors} error(s) found.")
        return 1
    print("\nAll ontology files valid.")
    return 0


if __name__ == "__main__":
    sys.exit(validate())
