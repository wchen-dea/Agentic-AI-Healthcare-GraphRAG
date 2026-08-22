#!/usr/bin/env python3
"""Validate terminology mapping coverage for producer vocabularies.

This script enforces minimum mapping coverage thresholds for:
- Lab names (LOINC-oriented local mappings)
- CPT procedure codes
- ICD-10 diagnosis codes
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PLATFORM_DIR = Path(__file__).resolve().parents[3] / "data-platform" / "healthcare"
PRODUCER_FILE = DATA_PLATFORM_DIR / "producer" / "produce_events.py"

LAB_MAPPINGS_FILE = DATA_PLATFORM_DIR / "config" / "ontology" / "lab_mappings.yaml"
CPT_MAPPINGS_FILE = DATA_PLATFORM_DIR / "config" / "ontology" / "cpt_mappings.yaml"
ICD10_MAPPINGS_FILE = DATA_PLATFORM_DIR / "config" / "ontology" / "icd10_mappings.yaml"

LAB_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_LABS", "0.95"))
CPT_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_CPT", "0.95"))
ICD10_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_ICD10", "0.95"))


def _extract_producer_sets() -> tuple[set[str], set[str], set[str]]:
    source = PRODUCER_FILE.read_text(encoding="utf-8")
    module = ast.parse(source)
    labs: set[str] = set()
    cpt_codes: set[str] = set()
    icd10_codes: set[str] = set()

    for node in module.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id == "LAB_TESTS" and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if isinstance(item, ast.Tuple) and item.elts and isinstance(item.elts[0], ast.Constant):
                        labs.add(str(item.elts[0].value).strip())
            elif target.id == "PROCEDURE_CODES" and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if isinstance(item, ast.Tuple) and item.elts and isinstance(item.elts[0], ast.Constant):
                        cpt_codes.add(str(item.elts[0].value).strip())
            elif target.id == "DIAGNOSIS_CODES" and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if isinstance(item, ast.Constant):
                        icd10_codes.add(str(item.value).strip())

    return labs, cpt_codes, icd10_codes


def _extract_local_codes_from_yaml(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    matches = re.findall(r"^\s*-\s*local_code:\s*(.+?)\s*$", text, re.MULTILINE)
    result: set[str] = set()
    for raw in matches:
        cleaned = raw.strip().strip("\"").strip("'")
        if cleaned:
            result.add(cleaned)
    return result


def _coverage(name: str, source: set[str], mapped: set[str], threshold: float) -> tuple[bool, str]:
    if not source:
        return False, f"{name}: no source values found"

    covered = source.intersection(mapped)
    missing = sorted(source - mapped)
    ratio = len(covered) / len(source)
    status = ratio >= threshold

    summary = (
        f"{name}: {len(covered)}/{len(source)} covered ({ratio:.1%}) "
        f"threshold={threshold:.0%}"
    )
    if missing:
        summary += f"; missing={', '.join(missing[:10])}"
        if len(missing) > 10:
            summary += f" ... (+{len(missing) - 10} more)"
    return status, summary


def main() -> int:
    labs, cpt_codes, icd10_codes = _extract_producer_sets()
    mapped_labs = _extract_local_codes_from_yaml(LAB_MAPPINGS_FILE)
    mapped_cpt = _extract_local_codes_from_yaml(CPT_MAPPINGS_FILE)
    mapped_icd10 = _extract_local_codes_from_yaml(ICD10_MAPPINGS_FILE)

    checks = [
        _coverage("LAB", labs, mapped_labs, LAB_THRESHOLD),
        _coverage("CPT", cpt_codes, mapped_cpt, CPT_THRESHOLD),
        _coverage("ICD10", icd10_codes, mapped_icd10, ICD10_THRESHOLD),
    ]

    print("Terminology coverage report")
    failures = 0
    for ok, summary in checks:
        print(f"- {'PASS' if ok else 'FAIL'} {summary}")
        if not ok:
            failures += 1

    if failures:
        print("Coverage validation failed.")
        return 1

    print("Coverage validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
