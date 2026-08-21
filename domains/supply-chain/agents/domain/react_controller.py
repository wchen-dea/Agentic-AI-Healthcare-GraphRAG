from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .models import RequestType, RetrievalPlan


@dataclass(frozen=True)
class ReactLoopSettings:
    max_iterations: int = 3
    min_confidence: float = 0.75
    max_no_progress_steps: int = 1


@dataclass(frozen=True)
class ReactStep:
    iteration: int
    action: str
    plan_name: str
    top_k: int
    new_event_ids: int
    new_patient_ids: int
    confidence_after: float


def run_react_query_loop(
    *,
    question: str,
    patient_id: str | None,
    context_limit: int,
    settings: ReactLoopSettings,
    classify_request_type_fn: Callable[[str, str | None], RequestType],
    select_retrieval_plan_fn: Callable[[RequestType, str, str | None, int], RetrievalPlan],
    vector_context_fn: Callable[[str, str | None, int], list[dict[str, Any]]],
    rank_vector_context_fn: Callable[[list[dict[str, Any]], RequestType], list[dict[str, Any]]],
    graph_context_fn: Callable[[list[str]], list[dict[str, Any]]],
    rank_graph_context_fn: Callable[[list[dict[str, Any]], RequestType], list[dict[str, Any]]],
    synthesize_answer_fn: Callable[[str, list[dict[str, Any]], list[dict[str, Any]]], str],
) -> dict[str, Any]:
    seen_event_ids: set[str] = set()
    seen_graph_patient_ids: set[str] = set()
    merged_vector: list[dict[str, Any]] = []
    merged_graph: list[dict[str, Any]] = []
    steps: list[ReactStep] = []

    no_progress_count = 0
    request_type: RequestType = "patient_summary"
    last_plan: RetrievalPlan | None = None
    final_reason = "max_iterations_reached"
    confidence = 0.0

    for iteration in range(max(1, settings.max_iterations)):
        request_type = classify_request_type_fn(question, patient_id)
        plan = select_retrieval_plan_fn(request_type, question, patient_id, context_limit)
        last_plan = plan

        vector_items_raw = vector_context_fn(plan.query_text, patient_id, plan.top_k)
        vector_items = rank_vector_context_fn(vector_items_raw, request_type)

        patient_ids = [
            value
            for value in {item.get("patient_id") for item in vector_items if item.get("patient_id")}
            if value
        ]
        if patient_id and patient_id not in patient_ids:
            patient_ids.append(patient_id)

        graph_items_raw = graph_context_fn(patient_ids) if patient_ids else []
        graph_items = rank_graph_context_fn(graph_items_raw, request_type)

        new_event_ids = _merge_vector_context(merged_vector, vector_items, seen_event_ids)
        new_patient_ids = _merge_graph_context(merged_graph, graph_items, seen_graph_patient_ids)

        if new_event_ids == 0 and new_patient_ids == 0:
            no_progress_count += 1
        else:
            no_progress_count = 0

        confidence = _estimate_confidence(merged_vector, merged_graph)
        steps.append(
            ReactStep(
                iteration=iteration,
                action="vector_and_graph_retrieve",
                plan_name=plan.name,
                top_k=plan.top_k,
                new_event_ids=new_event_ids,
                new_patient_ids=new_patient_ids,
                confidence_after=confidence,
            )
        )

        if confidence >= settings.min_confidence and merged_vector and merged_graph:
            final_reason = "confidence_reached"
            break
        if no_progress_count > settings.max_no_progress_steps:
            final_reason = "no_progress_limit"
            break

    answer = synthesize_answer_fn(question, merged_vector, merged_graph)

    response: dict[str, Any] = {
        "question": question,
        "request_type": request_type,
        "retrieval_plan": {
            "name": last_plan.name if last_plan else "patient_summary",
            "top_k": last_plan.top_k if last_plan else context_limit,
            "reason": last_plan.reason if last_plan else "ReAct fallback plan.",
        },
        "patients": sorted(seen_graph_patient_ids),
        "vector_context": merged_vector,
        "graph_context": merged_graph,
        "answer": answer,
        "react": {
            "enabled": True,
            "iterations": len(steps),
            "final_reason": final_reason,
            "confidence": confidence,
            "actions": [
                {
                    "iteration": step.iteration,
                    "action": step.action,
                    "plan_name": step.plan_name,
                    "top_k": step.top_k,
                    "new_event_ids": step.new_event_ids,
                    "new_patient_ids": step.new_patient_ids,
                    "confidence_after": step.confidence_after,
                }
                for step in steps
            ],
        },
    }
    return response


def _merge_vector_context(
    merged: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    seen_event_ids: set[str],
) -> int:
    added = 0
    for item in new_items:
        event_id = item.get("event_id")
        if not event_id:
            merged.append(item)
            added += 1
            continue
        if event_id in seen_event_ids:
            continue
        seen_event_ids.add(str(event_id))
        merged.append(item)
        added += 1
    return added


def _merge_graph_context(
    merged: list[dict[str, Any]],
    new_items: list[dict[str, Any]],
    seen_patient_ids: set[str],
) -> int:
    added = 0
    for item in new_items:
        patient_id = item.get("patient_id")
        if not patient_id:
            merged.append(item)
            added += 1
            continue
        pid = str(patient_id)
        if pid in seen_patient_ids:
            continue
        seen_patient_ids.add(pid)
        merged.append(item)
        added += 1
    return added


def _estimate_confidence(
    vector_items: list[dict[str, Any]],
    graph_items: list[dict[str, Any]],
) -> float:
    if vector_items and graph_items:
        return 1.0
    if vector_items or graph_items:
        return 0.5
    return 0.0
