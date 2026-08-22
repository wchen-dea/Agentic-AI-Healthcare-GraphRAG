"""Automated evaluation gates for CI/CD quality enforcement.

Runs the evaluation suite and fails if scores drop below configured thresholds.
Use in CI to block deployment when quality regresses.

Usage:
    python -m domain.evaluation_gates --mode single_pass --min-score 0.6
    python -m domain.evaluation_gates --mode langgraph --min-score 0.7
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from typing import Any


@dataclass
class GateThresholds:
    min_routing_accuracy: float = 0.6
    min_evidence_completeness: float = 0.5
    min_answer_quality: float = 0.5
    min_overall_score: float = 0.55


@dataclass
class GateResult:
    passed: bool
    overall_score: float
    routing_score: float
    evidence_score: float
    answer_score: float
    cases_evaluated: int
    failures: list[str]


def evaluate_with_gates(
    evaluation_results: list[dict[str, Any]],
    thresholds: GateThresholds | None = None,
) -> GateResult:
    """Score evaluation results against quality gates."""
    if thresholds is None:
        thresholds = GateThresholds()

    if not evaluation_results:
        return GateResult(
            passed=False, overall_score=0.0, routing_score=0.0,
            evidence_score=0.0, answer_score=0.0, cases_evaluated=0,
            failures=["No evaluation results to score"],
        )

    routing_scores: list[float] = []
    evidence_scores: list[float] = []
    answer_scores: list[float] = []

    for result in evaluation_results:
        routing_scores.append(result.get("routing", {}).get("score", 0.0))
        evidence_scores.append(result.get("evidence", {}).get("score", 0.0))
        answer_scores.append(result.get("answer_quality", {}).get("score", 0.0))

    avg_routing = sum(routing_scores) / len(routing_scores) if routing_scores else 0.0
    avg_evidence = sum(evidence_scores) / len(evidence_scores) if evidence_scores else 0.0
    avg_answer = sum(answer_scores) / len(answer_scores) if answer_scores else 0.0
    overall = (avg_routing + avg_evidence + avg_answer) / 3

    failures: list[str] = []
    if avg_routing < thresholds.min_routing_accuracy:
        failures.append(f"routing_accuracy={avg_routing:.2f} < {thresholds.min_routing_accuracy}")
    if avg_evidence < thresholds.min_evidence_completeness:
        failures.append(f"evidence_completeness={avg_evidence:.2f} < {thresholds.min_evidence_completeness}")
    if avg_answer < thresholds.min_answer_quality:
        failures.append(f"answer_quality={avg_answer:.2f} < {thresholds.min_answer_quality}")
    if overall < thresholds.min_overall_score:
        failures.append(f"overall_score={overall:.2f} < {thresholds.min_overall_score}")

    return GateResult(
        passed=len(failures) == 0,
        overall_score=overall,
        routing_score=avg_routing,
        evidence_score=avg_evidence,
        answer_score=avg_answer,
        cases_evaluated=len(evaluation_results),
        failures=failures,
    )


def print_report(result: GateResult, mode: str) -> None:
    """Print a human-readable quality gate report."""
    status = "PASS" if result.passed else "FAIL"
    print(f"\n{'='*60}")
    print(f"  Evaluation Quality Gate: {status} ({mode})")
    print(f"{'='*60}")
    print(f"  Cases evaluated:       {result.cases_evaluated}")
    print(f"  Overall score:         {result.overall_score:.2f}")
    print(f"  Routing accuracy:      {result.routing_score:.2f}")
    print(f"  Evidence completeness: {result.evidence_score:.2f}")
    print(f"  Answer quality:        {result.answer_score:.2f}")
    if result.failures:
        print(f"\n  Failures:")
        for f in result.failures:
            print(f"    - {f}")
    print(f"{'='*60}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run evaluation quality gates")
    parser.add_argument("--mode", default="single_pass", choices=["single_pass", "react", "langgraph"])
    parser.add_argument("--min-score", type=float, default=0.55, help="Minimum overall score to pass")
    parser.add_argument("--min-routing", type=float, default=0.6)
    parser.add_argument("--min-evidence", type=float, default=0.5)
    parser.add_argument("--min-answer", type=float, default=0.5)
    parser.add_argument("--results-file", help="JSON file with pre-computed evaluation results")
    args = parser.parse_args()

    thresholds = GateThresholds(
        min_routing_accuracy=args.min_routing,
        min_evidence_completeness=args.min_evidence,
        min_answer_quality=args.min_answer,
        min_overall_score=args.min_score,
    )

    if args.results_file:
        with open(args.results_file) as f:
            evaluation_results = json.load(f)
    else:
        # Run live evaluation (requires running stack)
        from langgraph_agents.evaluation import run_evaluation_suite
        from app import run_query
        evaluation_results = run_evaluation_suite(run_query, mode=args.mode)

    result = evaluate_with_gates(evaluation_results, thresholds)
    print_report(result, args.mode)

    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
