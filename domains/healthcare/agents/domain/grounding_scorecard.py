"""Grounded-answer scorecard.

Evaluates LLM answers for grounding quality:
- unsupported_claim_rate: fraction of claims not backed by context
- citation_coverage: fraction of context items referenced in the answer
- has_safety_caveat: whether the answer includes a clinical disclaimer
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class GroundingScore:
    unsupported_claim_rate: float
    citation_coverage: float
    has_safety_caveat: bool
    claim_count: int
    supported_count: int
    context_items: int
    cited_items: int


_CAVEAT_PATTERNS = re.compile(
    r"(not medical advice|clinical review|consult|disclaimer|advisory.only|independent.*review|safety caveat)",
    re.IGNORECASE,
)

_CLAIM_SPLITTER = re.compile(r"[.!?]\s+")


def score_grounding(answer: str, context_texts: list[str]) -> GroundingScore:
    """Score how well an answer is grounded in the provided context."""
    claims = [c.strip() for c in _CLAIM_SPLITTER.split(answer) if len(c.strip()) > 15]
    claim_count = len(claims)

    context_lower = [t.lower() for t in context_texts if t]
    context_keywords: list[set[str]] = []
    for ctx in context_lower:
        words = set(re.findall(r"\b[a-z]{3,}\b", ctx))
        context_keywords.append(words)

    supported = 0
    for claim in claims:
        claim_words = set(re.findall(r"\b[a-z]{3,}\b", claim.lower()))
        if not claim_words:
            supported += 1
            continue
        for kw_set in context_keywords:
            overlap = len(claim_words & kw_set) / len(claim_words) if claim_words else 0
            if overlap >= 0.3:
                supported += 1
                break

    cited = 0
    answer_lower = answer.lower()
    for ctx in context_lower:
        key_terms = set(re.findall(r"\b[a-z]{4,}\b", ctx))
        if not key_terms:
            continue
        matches = sum(1 for t in key_terms if t in answer_lower)
        if matches >= min(3, len(key_terms)):
            cited += 1

    unsupported_rate = (claim_count - supported) / claim_count if claim_count else 0.0
    coverage = cited / len(context_texts) if context_texts else 1.0

    return GroundingScore(
        unsupported_claim_rate=unsupported_rate,
        citation_coverage=coverage,
        has_safety_caveat=bool(_CAVEAT_PATTERNS.search(answer)),
        claim_count=claim_count,
        supported_count=supported,
        context_items=len(context_texts),
        cited_items=cited,
    )
