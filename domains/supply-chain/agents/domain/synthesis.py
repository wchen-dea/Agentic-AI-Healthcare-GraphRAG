"""Prompt construction and LLM synthesis for supply-chain domain."""
from __future__ import annotations

from typing import Any


def build_synthesis_prompt(
    question: str,
    vector_ctx: list[dict[str, Any]],
    graph_ctx: list[dict[str, Any]],
    max_items: int = 5,
) -> str:
    vector_brief = _compact_vector(vector_ctx, max_items)
    graph_brief = _compact_graph(graph_ctx, max_items)

    return f"""
You are a supply-chain intelligence assistant for synthetic demo data only.
Do not provide final operational directives. Summarize likely context and evidence.

Question:
{question}

Vector context from Qdrant:
{vector_brief}

Graph context from Neo4j:
{graph_brief}

Answer with:
1. Key findings
2. Supply-chain relationship reasoning
3. Evidence snippets
4. Operational caveat
"""


def _compact_vector(items: list[dict[str, Any]], max_items: int) -> str:
    if not items:
        return "- none"
    lines = []
    for item in items[:max_items]:
        lines.append(
            f"- entity={item.get('entity_id', 'unknown')} "
            f"event={item.get('event_type', 'unknown')} "
            f"score={float(item.get('score', 0.0)):.3f}"
        )
    return "\n".join(lines)


def _compact_graph(items: list[dict[str, Any]], max_items: int) -> str:
    if not items:
        return "- none"
    chunks = []
    for supplier in items[:max_items]:
        sid = supplier.get("supplier_id", "unknown")
        name = supplier.get("name", "?")
        country = supplier.get("country", "?")
        risk_tier = supplier.get("risk_tier", "?")
        parts = ", ".join(p.get("part", "?") for p in (supplier.get("parts") or [])[:5]) or "none"
        signals = "; ".join(
            f"{s.get('signal', '?')} [{s.get('severity', '?')}]"
            for s in (supplier.get("risk_signals") or [])[:3]
        ) or "none"
        chunks.append(
            f"- supplier={sid} name={name} country={country} risk={risk_tier}\n"
            f"  parts={parts}\n"
            f"  risk_signals={signals}"
        )
    return "\n".join(chunks)


def synthesize_answer(
    question: str,
    vector_ctx: list[dict[str, Any]],
    graph_ctx: list[dict[str, Any]],
    llm_provider,
    *,
    timeout_seconds: int = 120,
    max_tokens: int = 1200,
    max_items: int = 5,
) -> str:
    prompt = build_synthesis_prompt(question, vector_ctx, graph_ctx, max_items)
    return llm_provider.generate(
        prompt=prompt,
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
        temperature=0.2,
    )
