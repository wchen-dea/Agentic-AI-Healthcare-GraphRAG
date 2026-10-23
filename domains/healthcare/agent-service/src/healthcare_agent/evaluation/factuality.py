"""Deterministic claim-level factuality scorer.

Extracts named clinical claims (drugs, labs, conditions) from an answer and
checks that each is supported by the retrieved evidence. It detects unsupported
named entities, not arbitrary semantic errors; there is no network or model call.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

__all__ = ["CLAIM_TERMS", "Claim", "extract_claims", "score_factuality"]

# Canonical term -> accepted surface forms. Kept in step with
# knowledge/ontology/vocabularies.yaml (guarded by a unit test).
CLAIM_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "drug": {
        "warfarin": ("warfarin",),
        "metformin": ("metformin",),
        "lisinopril": ("lisinopril",),
        "spironolactone": ("spironolactone",),
        "ibuprofen": ("ibuprofen",),
        "insulin": ("insulin",),
        "amoxicillin": ("amoxicillin",),
        "atorvastatin": ("atorvastatin",),
    },
    "lab": {
        "potassium": ("potassium",),
        "glucose": ("glucose",),
        "hba1c": ("hba1c", "hemoglobin a1c"),
        "troponin i": ("troponin i", "troponin"),
        "creatinine": ("creatinine",),
        "egfr": ("egfr",),
    },
    "condition": {
        "hyperkalemia": ("hyperkalemia",),
        "chronic kidney disease": ("chronic kidney disease", "ckd"),
        "diabetes mellitus": ("diabetes mellitus", "diabetes"),
        "cough": ("cough",),
        "palpitations": ("palpitations",),
        "shortness of breath": ("shortness of breath",),
    },
}


@dataclass(frozen=True)
class Claim:
    kind: str
    term: str


def _pattern(form: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", re.I)


def _forms(terms: Mapping[str, Mapping[str, tuple[str, ...]]]) -> Iterable[tuple[str, str, tuple[str, ...]]]:
    for kind, entries in terms.items():
        for canonical, forms in entries.items():
            yield kind, canonical, forms


def extract_claims(
    text: str, terms: Mapping[str, Mapping[str, tuple[str, ...]]] | None = None,
) -> list[Claim]:
    """Return the distinct named clinical claims mentioned in ``text`` (sorted for determinism)."""
    claims = {
        Claim(kind, canonical)
        for kind, canonical, forms in _forms(terms or CLAIM_TERMS)
        if any(_pattern(f).search(text) for f in forms)
    }
    return sorted(claims, key=lambda c: (c.kind, c.term))


def _flatten(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for item in value.values():
            yield from _flatten(item)
    elif isinstance(value, (list, tuple, set)):
        for item in value:
            yield from _flatten(item)


def score_factuality(
    answer: str,
    vector_ctx: list[dict[str, Any]],
    graph_ctx: list[dict[str, Any]],
    *,
    terms: Mapping[str, Mapping[str, tuple[str, ...]]] | None = None,
) -> dict[str, Any]:
    """Score the share of answer claims supported by evidence (1.0 when there are no claims)."""
    active = terms or CLAIM_TERMS
    evidence_text = " ".join(_flatten([vector_ctx, graph_ctx]))
    forms_by_claim = {(k, c): forms for k, c, forms in _forms(active)}

    claims = extract_claims(answer, active)
    unsupported = [
        c.term
        for c in claims
        if not any(_pattern(f).search(evidence_text) for f in forms_by_claim[(c.kind, c.term)])
    ]
    score = 1.0 if not claims else (len(claims) - len(unsupported)) / len(claims)
    return {
        "metric": "factuality",
        "claims": len(claims),
        "unsupported_claims": unsupported,
        "score": score,
    }
