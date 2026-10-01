from __future__ import annotations

from typing import Any


def _compare(operator: str, actual: float, expected: float) -> bool:
    if operator == "gt":
        return actual > expected
    if operator == "gte":
        return actual >= expected
    if operator == "lt":
        return actual < expected
    if operator == "lte":
        return actual <= expected
    if operator == "eq":
        return actual == expected
    raise ValueError(f"Unsupported operator '{operator}'")


def _to_float(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def evaluate_lab_signal_rules(
    rules: list[dict[str, Any]],
    observation_name: str | None,
    value: Any,
    *,
    event_type: str = "LAB_RESULT",
) -> list[dict[str, str]]:
    if observation_name is None or value is None:
        return []

    numeric_value = _to_float(value)
    matches: list[dict[str, str]] = []
    for rule in rules:
        trigger = rule.get("trigger", {})
        condition = rule.get("condition", {})
        output_edge = rule.get("output_edge", {})
        if trigger.get("event_type") != event_type:
            continue
        if trigger.get("observation_name") != observation_name:
            continue
        if not _compare(condition.get("operator", "eq"), numeric_value, _to_float(condition.get("value"))):
            continue
        matches.append(
            {
                "rule_id": str(rule.get("id")),
                "condition": str(output_edge.get("condition")),
                "reason": str(output_edge.get("reason")),
            }
        )
    return matches


def evaluate_claims_outcome_rules(
    rules: list[dict[str, Any]],
    *,
    event_type: str,
    claim_type: str | None,
    procedure_code: str | None,
) -> list[dict[str, str]]:
    matches: list[dict[str, str]] = []
    for rule in rules:
        trigger = rule.get("trigger", {})
        output_edge = rule.get("output_edge", {})
        if trigger.get("event_type") != event_type:
            continue
        if trigger.get("claim_type") is not None and trigger.get("claim_type") != claim_type:
            continue
        procedure_codes = trigger.get("procedure_code_in")
        if procedure_codes is not None and procedure_code not in procedure_codes:
            continue
        matches.append(
            {
                "rule_id": str(rule.get("id")),
                "type": str(output_edge.get("type")),
                "adverse_outcome": str(output_edge.get("adverse_outcome")),
            }
        )
    return matches