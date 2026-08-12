from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ontology_dir() -> Path:
    configured = os.getenv("ONTOLOGY_CONFIG_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return _repo_root() / "config" / "ontology"


def _read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at {path}")
    return data


def _ensure_unique_ids(items: list[dict[str, Any]], field: str, label: str) -> None:
    seen: set[str] = set()
    for item in items:
        value = item.get(field)
        if not value:
            raise ValueError(f"Missing '{field}' in {label}")
        if value in seen:
            raise ValueError(f"Duplicate {label} '{value}'")
        seen.add(str(value))


def _load_rule_packs(base_dir: Path) -> dict[str, dict[str, Any]]:
    packs: dict[str, dict[str, Any]] = {}
    for path in sorted((base_dir / "rules").glob("*.yaml")):
        packs[path.stem] = _read_yaml(path)
    return packs


def _merge_local_mappings(target: dict[str, Any], source: dict[str, Any]) -> None:
    target_mappings = target.setdefault("local_mappings", {})
    for key, values in source.get("local_mappings", {}).items():
        target_mappings[key] = list(values)


@lru_cache(maxsize=4)
def load_ontology_bundle(base_dir: str | None = None) -> dict[str, Any]:
    root = Path(base_dir).expanduser().resolve() if base_dir else ontology_dir()
    entities = _read_yaml(root / "entities.yaml")
    relationships = _read_yaml(root / "relationships.yaml")
    vocabularies = _read_yaml(root / "vocabularies.yaml")
    patient_mappings = _read_yaml(root / "patient_mappings.yaml")
    medication_mappings = _read_yaml(root / "medication_mappings.yaml")
    provider_mappings = _read_yaml(root / "provider_mappings.yaml")
    device_mappings = _read_yaml(root / "device_mappings.yaml")
    payer_mappings = _read_yaml(root / "payer_mappings.yaml")
    provenance = _read_yaml(root / "provenance.yaml")
    graph_seeds = _read_yaml(root / "graph_seeds.yaml")
    rule_packs = _load_rule_packs(root)

    _merge_local_mappings(vocabularies, patient_mappings)
    _merge_local_mappings(vocabularies, medication_mappings)
    _merge_local_mappings(vocabularies, provider_mappings)
    _merge_local_mappings(vocabularies, device_mappings)
    _merge_local_mappings(vocabularies, payer_mappings)

    entity_items = entities.get("entities", [])
    relationship_items = relationships.get("relationships", [])
    provenance_items = provenance.get("source_system_classes", [])

    _ensure_unique_ids(entity_items, "id", "entity id")
    _ensure_unique_ids(rule_packs.get("lab_signals", {}).get("rules", []), "id", "lab rule id")
    _ensure_unique_ids(rule_packs.get("claims_outcomes", {}).get("rules", []), "id", "claims rule id")

    return {
        "base_dir": root,
        "version": entities.get("version") or relationships.get("version") or "unknown",
        "entities": entity_items,
        "entities_by_canonical_name": {
            item["canonical_name"]: item for item in entity_items if item.get("canonical_name")
        },
        "relationships": relationship_items,
        "relationship_types": {item["type"] for item in relationship_items if item.get("type")},
        "vocabularies": vocabularies,
        "provenance": provenance_items,
        "provenance_by_source_type": {
            item["source_type"]: item for item in provenance_items if item.get("source_type")
        },
        "graph_seeds": graph_seeds,
        "rule_packs": rule_packs,
    }


def load_lab_signal_rules(bundle: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    source = bundle or load_ontology_bundle()
    return list(source["rule_packs"].get("lab_signals", {}).get("rules", []))


def load_claims_outcome_rules(bundle: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    source = bundle or load_ontology_bundle()
    return list(source["rule_packs"].get("claims_outcomes", {}).get("rules", []))


def load_drug_safety_rules(bundle: dict[str, Any] | None = None) -> dict[str, Any]:
    source = bundle or load_ontology_bundle()
    return dict(source["rule_packs"].get("drug_safety", {}))


def vocabulary_mapping_index(
    bundle: dict[str, Any] | None,
    category: str,
) -> dict[str, dict[str, Any]]:
    source = bundle or load_ontology_bundle()
    items = source.get("vocabularies", {}).get("local_mappings", {}).get(category, [])
    mapping: dict[str, dict[str, Any]] = {}
    for item in items:
        local_code = item.get("local_code")
        if local_code:
            mapping[str(local_code).casefold()] = dict(item)
    return mapping


def provenance_for_source_type(
    bundle: dict[str, Any] | None,
    source_type: str | None,
) -> dict[str, Any]:
    source = bundle or load_ontology_bundle()
    if not source_type:
        return {}
    return dict(source["provenance_by_source_type"].get(source_type, {}))