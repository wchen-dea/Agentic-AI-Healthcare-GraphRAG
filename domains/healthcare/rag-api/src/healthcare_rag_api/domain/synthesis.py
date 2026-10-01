"""Prompt construction and LLM synthesis.

Extracted from app.py to decouple prompt logic from HTTP/MCP concerns.
"""
from __future__ import annotations

from typing import Any


def compact_vector_context(
    vector_ctx: list[dict[str, Any]], max_items: int = 5,
) -> str:
    if not vector_ctx:
        return "- none"
    lines: list[str] = []
    for item in vector_ctx[:max_items]:
        lines.append(
            "- "
            f"patient={item.get('patient_id', 'unknown')} "
            f"event={item.get('event_type', 'unknown')} "
            f"score={float(item.get('score', 0.0)):.3f}"
        )
    return "\n".join(lines)


def compact_graph_context(
    graph_ctx: list[dict[str, Any]], max_items: int = 5,
) -> str:
    if not graph_ctx:
        return "- none"

    chunks: list[str] = []
    for patient in graph_ctx[:max_items]:
        patient_id = patient.get("patient_id", "unknown")
        age = patient.get("age", "?")
        sex = patient.get("sex", "?")
        risk_tier = patient.get("risk_tier", "?")
        raw_conditions = patient.get("conditions", [])[:5]
        conditions = ", ".join(
            c.get("name", c) if isinstance(c, dict) else str(c) for c in raw_conditions
        ) or "none"
        symptoms = ", ".join(patient.get("symptoms", [])[:5]) or "none"

        observations = patient.get("observations", [])[:3]
        observation_summary = "; ".join(
            f"{obs.get('name', 'unknown')}={obs.get('value', 'n/a')}{obs.get('unit', '')}"
            for obs in observations
        ) or "none"

        medications = patient.get("medications", [])[:3]
        medication_summary = "; ".join(
            f"{med.get('medication', 'unknown')} {med.get('dose', '')} {med.get('route', '')}".strip()
            for med in medications
        ) or "none"

        interactions = [i for i in patient.get("interactions", [])[:3] if i.get("to")]
        interaction_summary = "; ".join(
            f"{i.get('from', '?')}+{i.get('to', '?')} ({i.get('risk', '?')}/{i.get('severity', '?')})"
            for i in interactions
        ) or "none"

        lab_signals = patient.get("lab_signals", [])[:5]
        lab_signal_summary = "; ".join(
            f"{s.get('observation', '?')}={s.get('value', '?')} \u2192 {s.get('indicated_condition', '?')}"
            for s in lab_signals
        ) or "none"

        vitals_alerts = [v.get("alert") for v in patient.get("vitals", [])[:5] if v.get("alert")]
        alert_summary = "; ".join(vitals_alerts) or "none"

        adverse_events = patient.get("adverse_events", [])[:3]
        adverse_summary = "; ".join(
            f"{ae.get('symptom', '?')} \u2190 {ae.get('medication', '?')} [{ae.get('severity', '?')}]"
            for ae in adverse_events
        ) or "none"

        contraindications = patient.get("contraindications", [])[:3]
        contra_summary = "; ".join(
            f"{c.get('medication', '?')} \u26a0 {c.get('condition', '?')} ({c.get('reason', '?')})"
            for c in contraindications
        ) or "none"

        chunks.append(
            f"- patient={patient_id} age={age} sex={sex} risk={risk_tier}\n"
            f"  conditions={conditions}\n"
            f"  symptoms={symptoms}\n"
            f"  observations={observation_summary}\n"
            f"  lab_signals={lab_signal_summary}\n"
            f"  medications={medication_summary}\n"
            f"  drug_interactions={interaction_summary}\n"
            f"  adverse_events={adverse_summary}\n"
            f"  contraindications={contra_summary}\n"
            f"  device_alerts={alert_summary}"
        )

    return "\n".join(chunks)


def build_synthesis_prompt(
    question: str,
    vector_ctx: list[dict[str, Any]],
    graph_ctx: list[dict[str, Any]],
    max_items: int = 5,
) -> str:
    vector_brief = compact_vector_context(vector_ctx, max_items)
    graph_brief = compact_graph_context(graph_ctx, max_items)

    return f"""
You are a clinical decision-support RAG assistant for synthetic demo data only.
Do not provide final medical advice. Summarize likely context and evidence.

Question:
{question}

Vector context from Qdrant:
{vector_brief}

Graph context from Neo4j:
{graph_brief}

Answer with:
1. Key findings
2. Relationship-based reasoning
3. Evidence snippets
4. Safety caveat
"""


def synthesize_answer(
    question: str,
    vector_ctx: list[dict[str, Any]],
    graph_ctx: list[dict[str, Any]],
    llm_provider,
    *,
    timeout_seconds: int = 120,
    max_tokens: int = 1200,
    max_items: int = 5,
    use_harness: bool = True,
) -> str:
    from .harness import (
        RetryPolicy,
        call_with_retry,
        check_input_safety,
        check_output_grounding,
        check_output_safety,
        register_prompt,
    )

    input_guard = check_input_safety(question)
    if not input_guard.passed:
        return f"Input rejected: {', '.join(input_guard.reasons)}"

    prompt = build_synthesis_prompt(question, vector_ctx, graph_ctx, max_items)
    register_prompt("clinical_synthesis", "v1", prompt[:200])

    if not use_harness:
        return llm_provider.generate(
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            temperature=0.2,
        )

    result = call_with_retry(
        fn=lambda: llm_provider.generate(
            prompt=prompt,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            temperature=0.2,
        ),
        policy=RetryPolicy(max_retries=1, base_delay_seconds=2.0),
    )

    if not result.success:
        return result.output

    output_guard = check_output_safety(result.output)
    if not output_guard.passed:
        return f"Output blocked: {', '.join(output_guard.reasons)}"

    grounding = check_output_grounding(result.output, vector_ctx, graph_ctx)
    if not grounding.passed and "empty_answer" in grounding.reasons:
        return "Unable to generate a grounded answer from available evidence."

    return result.output
