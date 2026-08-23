#!/usr/bin/env python3
"""Validate terminology mapping coverage for producer vocabularies.

Enforces minimum mapping coverage thresholds for:
- Lab names → LOINC
- CPT procedure codes
- ICD-10 diagnosis codes (both DIAGNOSIS_CODES and DIAGNOSIS_TO_ICD10)
- Medications → RxNorm
- Provider specialties
- Payer names
Also flags any standard_code still set to 'TBD'.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_PLATFORM_DIR = Path(__file__).resolve().parents[3] / "platform" / "healthcare"
PRODUCER_FILE = DATA_PLATFORM_DIR / "producer" / "produce_events.py"
MAPPINGS_DIR = DATA_PLATFORM_DIR / "ontology" / "mappings"

LAB_MAPPINGS_FILE = MAPPINGS_DIR / "lab_mappings.yaml"
CPT_MAPPINGS_FILE = MAPPINGS_DIR / "cpt_mappings.yaml"
ICD10_MAPPINGS_FILE = MAPPINGS_DIR / "icd10_mappings.yaml"
MED_MAPPINGS_FILE = MAPPINGS_DIR / "medication_mappings.yaml"
PROVIDER_MAPPINGS_FILE = MAPPINGS_DIR / "provider_mappings.yaml"
PAYER_MAPPINGS_FILE = MAPPINGS_DIR / "payer_mappings.yaml"

LAB_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_LABS", "0.95"))
CPT_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_CPT", "0.95"))
ICD10_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_ICD10", "0.95"))
MED_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_MEDS", "0.90"))
PROVIDER_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_PROVIDERS", "0.90"))
PAYER_THRESHOLD = float(os.getenv("TERMINOLOGY_COVERAGE_THRESHOLD_PAYERS", "0.90"))


def _extract_producer_sets() -> dict[str, set[str]]:
    source = PRODUCER_FILE.read_text(encoding="utf-8")
    module = ast.parse(source)
    labs: set[str] = set()
    cpt_codes: set[str] = set()
    icd10_codes: set[str] = set()
    medications: set[str] = set()
    specialties: set[str] = set()
    payers: set[str] = set()

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
            elif target.id == "DIAGNOSIS_TO_ICD10" and isinstance(node.value, ast.Dict):
                for v in node.value.values:
                    if isinstance(v, ast.Constant):
                        icd10_codes.add(str(v.value).strip())
            elif target.id == "MEDICATIONS" and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if isinstance(item, ast.Tuple) and item.elts and isinstance(item.elts[0], ast.Constant):
                        medications.add(str(item.elts[0].value).strip())
            elif target.id == "PROVIDER_SPECIALTIES" and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if isinstance(item, ast.Constant):
                        specialties.add(str(item.value).strip().lower())
            elif target.id == "PAYERS" and isinstance(node.value, ast.List):
                for item in node.value.elts:
                    if isinstance(item, ast.Constant):
                        payers.add(str(item.value).strip().lower())

    return {
        "labs": labs,
        "cpt": cpt_codes,
        "icd10": icd10_codes,
        "medications": medications,
        "specialties": specialties,
        "payers": payers,
    }


def _extract_local_codes_from_yaml(path: Path, lowercase: bool = False) -> set[str]:
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    matches = re.findall(r"^\s*-\s*local_code:\s*(.+?)\s*$", text, re.MULTILINE)
    result: set[str] = set()
    for raw in matches:
        cleaned = raw.strip().strip("\"").strip("'")
        if cleaned:
            result.add(cleaned.lower() if lowercase else cleaned)
    return result


def _count_tbd(path: Path) -> int:
    if not path.exists():
        return 0
    text = path.read_text(encoding="utf-8")
    return len(re.findall(r"standard_code:\s*TBD", text))


def _coverage(name: str, source: set[str], mapped: set[str], threshold: float) -> tuple[bool, str]:
    if not source:
        return True, f"{name}: no source values found (skipped)"

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
    producer = _extract_producer_sets()
    mapped_labs = _extract_local_codes_from_yaml(LAB_MAPPINGS_FILE)
    mapped_cpt = _extract_local_codes_from_yaml(CPT_MAPPINGS_FILE)
    mapped_icd10 = _extract_local_codes_from_yaml(ICD10_MAPPINGS_FILE)
    mapped_meds = _extract_local_codes_from_yaml(MED_MAPPINGS_FILE)
    mapped_specialties = _extract_local_codes_from_yaml(PROVIDER_MAPPINGS_FILE, lowercase=True)
    mapped_payers = _extract_local_codes_from_yaml(PAYER_MAPPINGS_FILE, lowercase=True)

    checks = [
        _coverage("LAB→LOINC", producer["labs"], mapped_labs, LAB_THRESHOLD),
        _coverage("CPT", producer["cpt"], mapped_cpt, CPT_THRESHOLD),
        _coverage("ICD-10", producer["icd10"], mapped_icd10, ICD10_THRESHOLD),
        _coverage("MED→RxNorm", producer["medications"], mapped_meds, MED_THRESHOLD),
        _coverage("SPECIALTY", producer["specialties"], mapped_specialties, PROVIDER_THRESHOLD),
        _coverage("PAYER", producer["payers"], mapped_payers, PAYER_THRESHOLD),
    ]

    # Check for TBD standard codes
    tbd_counts: list[tuple[str, int]] = []
    for name, path in [
        ("lab_mappings", LAB_MAPPINGS_FILE),
        ("icd10_mappings", ICD10_MAPPINGS_FILE),
        ("medication_mappings", MED_MAPPINGS_FILE),
        ("provider_mappings", PROVIDER_MAPPINGS_FILE),
    ]:
        count = _count_tbd(path)
        if count:
            tbd_counts.append((name, count))

    print("Terminology coverage report")
    failures = 0
    for ok, summary in checks:
        print(f"  {'PASS' if ok else 'FAIL'} {summary}")
        if not ok:
            failures += 1

    if tbd_counts:
        print("TBD standard codes remaining:")
        for name, count in tbd_counts:
            print(f"  WARN {name}: {count} entries still have standard_code=TBD")

    if failures:
        print(f"Coverage validation failed ({failures} check(s)).")
        return 1

    print("Coverage validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
