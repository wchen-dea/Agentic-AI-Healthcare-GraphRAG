"""Structured output models for constrained LLM generation.

Provides Pydantic models that define the expected shape of clinical responses,
enabling JSON-mode generation and downstream programmatic consumption.
"""
from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, ValidationError

_MAX_ITEMS = 20
_MAX_TEXT = 1000
_FALLBACK_SUMMARY_CHARS = 300
_CODE_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")


_SEVERITY_ALIASES = {
    "critical": "high",
    "severe": "high",
    "major": "high",
    "medium": "moderate",
    "mild": "low",
    "minor": "low",
}


def _normalize_label(value: Any) -> Any:
    return value.strip().lower() if isinstance(value, str) else value


def _normalize_severity(value: Any) -> Any:
    label = _normalize_label(value)
    return _SEVERITY_ALIASES.get(label, label) if isinstance(label, str) else label


def _truncate_text(value: Any) -> Any:
    return value[:_MAX_TEXT] if isinstance(value, str) else value


def _truncate_list(value: Any) -> Any:
    return value[:_MAX_ITEMS] if isinstance(value, list) else value


Severity = Annotated[Literal["high", "moderate", "low"], BeforeValidator(_normalize_severity)]
EvidenceSource = Annotated[Literal["graph_fact", "vector_event_text"], BeforeValidator(_normalize_label)]
Text = Annotated[str, BeforeValidator(_truncate_text)]


class _LlmModel(BaseModel):
    """LLM output is untrusted: ignore unknown keys, trim strings, truncate oversized values."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class RiskFinding(_LlmModel):
    category: Text = Field(description="Risk category (e.g., drug_interaction, lab_signal, contraindication)")
    severity: Severity = Field(description="high, moderate, or low")
    description: Text = Field(description="Brief explanation of the risk")
    evidence_source: EvidenceSource = Field(description="graph_fact or vector_event_text")


class MedicationInteraction(_LlmModel):
    drug_a: Text
    drug_b: Text
    mechanism: Text = ""
    severity: Severity = "moderate"


class LabSignal(_LlmModel):
    observation: Text
    value: Text = ""
    indicated_condition: Text = ""
    reason: Text = ""


class StructuredClinicalResponse(_LlmModel):
    summary: Text = Field(description="1-2 sentence answer summary")
    key_findings: Annotated[list[Text], BeforeValidator(_truncate_list)] = Field(default_factory=list, description="Bullet-point findings")
    risks: Annotated[list[RiskFinding], BeforeValidator(_truncate_list)] = Field(default_factory=list)
    interactions: Annotated[list[MedicationInteraction], BeforeValidator(_truncate_list)] = Field(default_factory=list)
    lab_signals: Annotated[list[LabSignal], BeforeValidator(_truncate_list)] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_caveat: Text = "Advisory only. Requires independent clinical review."


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
    """Parse LLM output into a validated structured response.

    Invalid or non-conforming output degrades to a low-confidence response
    instead of raising, so callers always receive the documented shape.
    """
    text = _CODE_FENCE.sub("", raw.strip())
    try:
        return StructuredClinicalResponse.model_validate_json(text)
    except ValidationError:
        return StructuredClinicalResponse(
            summary=raw.strip()[:_FALLBACK_SUMMARY_CHARS],
            key_findings=["Unable to parse structured response from LLM"],
            confidence=0.1,
        )
