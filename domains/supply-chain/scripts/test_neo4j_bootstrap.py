#!/usr/bin/env python3
"""Smoke-test supply-chain Neo4j bootstrap by parsing the init and seeds Cypher files."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PLATFORM_DIR = Path(__file__).resolve().parents[3] / "platform" / "supply-chain"
NEO4J_DIR = DATA_PLATFORM_DIR / "neo4j"

INIT_FILE = NEO4J_DIR / "init.cypher"
SEEDS_FILE = NEO4J_DIR / "generated_ontology_seeds.cypher"


def check_file(path: Path) -> int:
    if not path.exists():
        print(f"FAIL: {path.name} not found")
        return 1
    text = path.read_text(encoding="utf-8")
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("//")]
    if not lines:
        print(f"FAIL: {path.name} is empty")
        return 1
    statements = [l for l in lines if l.endswith(";")]
    print(f"OK:   {path.name} — {len(statements)} statements")
    return 0


def main() -> int:
    errors = 0
    errors += check_file(INIT_FILE)
    errors += check_file(SEEDS_FILE)

    if errors:
        print(f"\n{errors} error(s).")
        return 1

    init_text = INIT_FILE.read_text(encoding="utf-8")
    expected_labels = ["Supplier", "Part", "Facility", "Shipment", "PurchaseOrder", "QualityInspection", "DisruptionEvent", "RiskSignal"]
    missing = [l for l in expected_labels if l not in init_text]
    if missing:
        print(f"FAIL: init.cypher missing constraints for: {', '.join(missing)}")
        return 1

    print(f"OK:   All {len(expected_labels)} expected constraints present")
    print("\nBootstrap smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
