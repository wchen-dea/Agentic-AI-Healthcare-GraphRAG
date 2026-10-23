"""Claim-level factuality scorer: determinism, support detection, and ontology coverage."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from healthcare_agent.evaluation.factuality import CLAIM_TERMS, extract_claims, score_factuality

VECTOR = [{"event_id": "e1", "text": "Potassium 5.9 in patient on Spironolactone"}]
GRAPH = [{"patient_id": "P-1", "conditions": ["Chronic Kidney Disease"]}]


def test_fully_supported_answer_scores_one() -> None:
    result = score_factuality("Elevated potassium with spironolactone and CKD.", VECTOR, GRAPH)
    assert result["score"] == 1.0
    assert result["unsupported_claims"] == []


def test_unsupported_claim_is_reported_by_name() -> None:
    result = score_factuality("Potassium is high; warfarin was also prescribed.", VECTOR, GRAPH)
    assert result["unsupported_claims"] == ["warfarin"]
    assert result["score"] == pytest.approx(0.5)


def test_no_claims_scores_one() -> None:
    assert score_factuality("Nothing specific to report.", VECTOR, GRAPH)["score"] == 1.0


def test_no_evidence_makes_claims_unsupported() -> None:
    assert score_factuality("Warfarin noted.", [], [])["score"] == 0.0


def test_scoring_is_deterministic_and_word_bounded() -> None:
    args = ("Potassium and warfarin.", VECTOR, GRAPH)
    assert score_factuality(*args) == score_factuality(*args)
    assert extract_claims("Insulinoma is rare.") == []


def test_claim_terms_cover_ontology_vocabularies() -> None:
    root = Path(__file__).resolve().parents[5]
    path = root / "domains/healthcare/knowledge/ontology/vocabularies.yaml"
    if not path.exists():
        pytest.skip("ontology not available")
    data = yaml.safe_load(path.read_text())["local_mappings"]
    known = {t for entries in CLAIM_TERMS.values() for t in entries}
    codes = {m["local_code"].lower() for group in data.values() for m in group}
    assert codes <= known
