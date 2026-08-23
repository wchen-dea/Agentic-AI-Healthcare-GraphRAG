#!/usr/bin/env python3
"""Detect ontology drift between mapping files, the ontology bundle, and generated seeds.

Checks:
1. All mapping files have matching version numbers (no version skew).
2. Generated seed Cypher is in sync with the ontology bundle.
3. No standard_code values are set to 'TBD'.
4. Every mapping file has status: active (not draft).
5. Mapping local_codes have no duplicates within a file.

Exit 0 if clean, 1 if drift is detected.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from collections import Counter
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parents[3] / "platform" / "healthcare"
MAPPINGS_DIR = PLATFORM_DIR / "ontology" / "mappings"
SEEDS_FILE = PLATFORM_DIR / "neo4j" / "generated_ontology_seeds.cypher"
GENERATOR_FILE = Path(__file__).resolve().parent / "generate_ontology_seed_cypher.py"
FLINK_APP_DIR = PLATFORM_DIR / "flink-app"

if str(FLINK_APP_DIR) not in sys.path:
    sys.path.insert(0, str(FLINK_APP_DIR))


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen", GENERATOR_FILE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_version_consistency() -> list[str]:
    """All mapping files should share the same version."""
    versions: dict[str, str] = {}
    for path in sorted(MAPPINGS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^version:\s*(.+)$", text, re.MULTILINE)
        if match:
            versions[path.name] = match.group(1).strip()
    if not versions:
        return ["No mapping files found"]
    unique = set(versions.values())
    if len(unique) > 1:
        detail = ", ".join(f"{f}={v}" for f, v in sorted(versions.items()))
        return [f"Version skew across mapping files: {detail}"]
    return []


def check_status_active() -> list[str]:
    """All mapping files should have status: active."""
    issues = []
    for path in sorted(MAPPINGS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        match = re.search(r"^status:\s*(.+)$", text, re.MULTILINE)
        if match and match.group(1).strip() != "active":
            issues.append(f"{path.name} has status '{match.group(1).strip()}' (expected 'active')")
    return issues


def check_no_tbd() -> list[str]:
    """No standard_code should be TBD."""
    issues = []
    for path in sorted(MAPPINGS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        count = len(re.findall(r"standard_code:\s*TBD", text))
        if count:
            issues.append(f"{path.name} has {count} TBD standard_code entries")
    return issues


def check_no_duplicate_local_codes() -> list[str]:
    """No duplicate local_code within a single mapping file."""
    issues = []
    for path in sorted(MAPPINGS_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        codes = re.findall(r"^\s*-?\s*local_code:\s*(.+?)\s*$", text, re.MULTILINE)
        cleaned = [c.strip().strip("\"'").lower() for c in codes]
        dupes = [code for code, count in Counter(cleaned).items() if count > 1]
        if dupes:
            issues.append(f"{path.name} has duplicate local_codes: {', '.join(dupes)}")
    return issues


def check_seed_sync() -> list[str]:
    """Generated seed Cypher must match committed file."""
    if not SEEDS_FILE.exists():
        return ["generated_ontology_seeds.cypher not found"]
    if not GENERATOR_FILE.exists():
        return ["generate_ontology_seed_cypher.py not found"]
    gen = _load_generator()
    bundle = gen.load_ontology_bundle()
    expected = gen.build_seed_cypher(bundle)
    actual = SEEDS_FILE.read_text(encoding="utf-8")
    if expected != actual:
        return ["generated_ontology_seeds.cypher is out of sync with ontology bundle"]
    return []


def main() -> int:
    all_issues: list[str] = []

    checks = [
        ("Version consistency", check_version_consistency),
        ("Status active", check_status_active),
        ("No TBD codes", check_no_tbd),
        ("No duplicate local_codes", check_no_duplicate_local_codes),
        ("Seed Cypher sync", check_seed_sync),
    ]

    for name, fn in checks:
        issues = fn()
        if issues:
            print(f"FAIL {name}:")
            for issue in issues:
                print(f"  - {issue}")
            all_issues.extend(issues)
        else:
            print(f"PASS {name}")

    if all_issues:
        print(f"\nOntology drift detected ({len(all_issues)} issue(s)).")
        return 1

    print("\nOntology governance checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
