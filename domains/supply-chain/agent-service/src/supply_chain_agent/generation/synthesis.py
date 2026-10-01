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


def _compact_vector(items: list[dict[str, Any]], max_items: int, snippet_chars: int = 240) -> str:
    if not items:
        return "- none"
    lines = []
    for item in items[:max_items]:
        snippet = " ".join(str(item.get("text") or "").split())[:snippet_chars]
        lines.append(
            f"- entity={item.get('entity_id', 'unknown')} "
            f"event={item.get('event_type', 'unknown')} "
            f"score={float(item.get('score') or 0.0):.3f}"
            + (f" text={snippet}" if snippet else "")
        )
    return "\n".join(lines)


def _join(values: list[dict[str, Any]] | None, render, limit: int) -> str:
    return "; ".join(render(v) for v in (values or [])[:limit]) or "none"


def _compact_graph(items: list[dict[str, Any]], max_items: int) -> str:
    if not items:
        return "- none"
    chunks = []
    for entity in items[:max_items]:
        parts = _join(entity.get("supplied_parts"), lambda p: f"{p.get('part_id', '?')}({p.get('criticality', '?')})", 5)
        signals = _join(entity.get("risk_signals"), lambda s: f"{s.get('category', '?')}: {s.get('description', '?')}", 3)
        disruptions = _join(entity.get("disruptions"), lambda d: f"{d.get('type', '?')} [{d.get('severity', '?')}]", 3)
        quality = _join(
            entity.get("quality_inspections"), lambda q: f"{q.get('result', '?')} defect={q.get('defect_rate', '?')}", 3
        )
        inventory = _join(
            entity.get("inventory"),
            lambda i: f"{i.get('part_id', '?')} on_hand={i.get('on_hand', '?')} below_reorder={i.get('below_reorder', '?')}",
            3,
        )
        chunks.append(
            f"- {entity.get('entity_type', 'entity')}={entity.get('entity_id', 'unknown')} "
            f"name={entity.get('name', '?')} country={entity.get('country', '?')} "
            f"risk_score={entity.get('risk_score', '?')} geo_risk={entity.get('geo_risk', '?')}\n"
            f"  supplied_parts={parts}\n"
            f"  risk_signals={signals}\n"
            f"  disruptions={disruptions}\n"
            f"  quality_inspections={quality}\n"
            f"  inventory={inventory}"
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
