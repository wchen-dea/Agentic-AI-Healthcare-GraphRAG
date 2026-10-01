"""Retrieval benchmark fixtures and scoring.

Provides labeled query fixtures and precision@k / recall@k computation
for the vector retrieval pipeline. Used as a CI quality gate.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

FIXTURES_FILE = Path(__file__).parent / "fixtures" / "retrieval_benchmark.json"


@dataclass
class BenchmarkResult:
    query: str
    precision_at_k: float
    recall_at_k: float
    expected_types: list[str]
    returned_types: list[str]
    k: int


def load_fixtures() -> list[dict[str, Any]]:
    return json.loads(FIXTURES_FILE.read_text())


def precision_at_k(returned: list[str], relevant: set[str], k: int) -> float:
    top_k = returned[:k]
    if not top_k:
        return 0.0
    return sum(1 for t in top_k if t in relevant) / len(top_k)


def recall_at_k(returned: list[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 1.0
    top_k = returned[:k]
    return sum(1 for t in top_k if t in relevant) / len(relevant)


def evaluate_fixture(fixture: dict[str, Any], returned_types: list[str], k: int = 5) -> BenchmarkResult:
    relevant = set(fixture["expected_event_types"])
    return BenchmarkResult(
        query=fixture["query"],
        precision_at_k=precision_at_k(returned_types, relevant, k),
        recall_at_k=recall_at_k(returned_types, relevant, k),
        expected_types=fixture["expected_event_types"],
        returned_types=returned_types[:k],
        k=k,
    )


def score_all(fixtures: list[dict], results_by_query: dict[str, list[str]], k: int = 5) -> dict[str, float]:
    """Score all fixtures, return aggregate metrics."""
    precisions = []
    recalls = []
    for fix in fixtures:
        returned = results_by_query.get(fix["query"], [])
        result = evaluate_fixture(fix, returned, k)
        precisions.append(result.precision_at_k)
        recalls.append(result.recall_at_k)
    n = len(fixtures)
    return {
        "mean_precision_at_k": sum(precisions) / n if n else 0.0,
        "mean_recall_at_k": sum(recalls) / n if n else 0.0,
        "fixture_count": n,
        "k": k,
    }
