"""Structured output models for constrained LLM generation.

Provides Pydantic models that define the expected shape of clinical responses,
enabling JSON-mode generation and downstream programmatic consumption.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RiskFinding(BaseModel):
    category: str = Field(description="Risk category (e.g., drug_interaction, lab_signal, contraindication)")
    severity: str = Field(description="high, moderate, or low")
    description: str = Field(description="Brief explanation of the risk")
    evidence_source: str = Field(description="graph_fact or vector_event_text")


class MedicationInteraction(BaseModel):
    drug_a: str
    drug_b: str
    mechanism: str = ""
    severity: str = "moderate"


class LabSignal(BaseModel):
    observation: str
    value: str = ""
    indicated_condition: str = ""
    reason: str = ""


class StructuredClinicalResponse(BaseModel):
    summary: str = Field(description="1-2 sentence answer summary")
    key_findings: list[str] = Field(default_factory=list, description="Bullet-point findings")
    risks: list[RiskFinding] = Field(default_factory=list)
    interactions: list[MedicationInteraction] = Field(default_factory=list)
    lab_signals: list[LabSignal] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_caveat: str = "Advisory only. Requires independent clinical review."


def build_structured_prompt(question: str, vector_summary: str, graph_summary: str) -> str:
    return f"""You are a clinical decision support system. Answer the question using ONLY the provided evidence.
Return your response as a JSON object matching this schema:
{{
  "summary": "1-2 sentence answer",
  "key_findings": ["finding 1", "finding 2"],
  "risks": [{{"category": "...", "severity": "high|moderate|low", "description": "...", "evidence_source": "graph_fact|vector_event_text"}}],
  "interactions": [{{"drug_a": "...", "drug_b": "...", "mechanism": "...", "severity": "..."}}],
  "lab_signals": [{{"observation": "...", "value": "...", "indicated_condition": "...", "reason": "..."}}],
  "confidence": 0.0-1.0,
  "safety_caveat": "Advisory only. Requires independent clinical review."
}}

Vector Evidence:
{vector_summary}

Graph Evidence:
{graph_summary}

Question: {question}

Respond ONLY with valid JSON. No markdown, no explanation outside the JSON."""


def parse_structured_response(raw: str) -> StructuredClinicalResponse:
    """Parse LLM output into a validated structured response."""
    import json

    text = raw.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        return StructuredClinicalResponse(**data)
    except (json.JSONDecodeError, ValueError):
        return StructuredClinicalResponse(
            summary=raw[:300],
            key_findings=["Unable to parse structured response from LLM"],
            confidence=0.1,
        )
