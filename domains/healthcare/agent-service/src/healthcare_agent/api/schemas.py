"""Request contracts for the HTTP API and MCP tools.

Size limits come from settings, which the composition root binds once with
``configure_request_limits``. Validators read the bound limits at validation
time, so the models stay static and importable without a settings instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


@dataclass(frozen=True)
class RequestLimits:
    max_question_chars: int = 1000
    max_context_items: int = 5

    @property
    def max_cohort_top_k(self) -> int:
        return max(self.max_context_items, 8)


_limits = RequestLimits()


def configure_request_limits(limits: RequestLimits) -> None:
    global _limits
    _limits = limits


def request_limits() -> RequestLimits:
    return _limits


def _check_question(value: str) -> str:
    if len(value) > _limits.max_question_chars:
        raise ValueError(f"question must be at most {_limits.max_question_chars} characters")
    return value


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _QuestionRequest(_Request):
    question: str = Field(min_length=3)

    @field_validator("question")
    @classmethod
    def _question_within_limit(cls, value: str) -> str:
        return _check_question(value)


class QueryRequest(_QuestionRequest):
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    structured: bool = Field(default=False, description="Return structured JSON response")
    session_id: str | None = Field(default=None, max_length=64)


class PatientContextGetRequest(_Request):
    patient_id: str = Field(min_length=1, max_length=128)
    include_claims: bool = True
    include_interactions: bool = True


class VectorEvidenceSearchRequest(_QuestionRequest):
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    top_k: int = Field(default=5, ge=1)

    @field_validator("top_k")
    @classmethod
    def _top_k_within_limit(cls, value: int) -> int:
        if value > _limits.max_context_items:
            raise ValueError(f"top_k must be at most {_limits.max_context_items}")
        return value


class GraphRagAnswerRequest(_QuestionRequest):
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    response_style: Literal["concise", "clinical", "audit"] = "concise"


class RiskSummaryRequest(_Request):
    patient_id: str = Field(min_length=1, max_length=128)
    time_window_hours: int = Field(default=72, ge=1, le=720)


class EvidenceBundleExportRequest(_QuestionRequest):
    patient_id: str | None = Field(default=None, min_length=1, max_length=128)
    include_raw_payload: bool = False


class TimelineExplainRequest(_Request):
    patient_id: str = Field(min_length=1, max_length=128)
    time_window_hours: int = Field(default=168, ge=1, le=720)


class MedicationRiskAssessRequest(_Request):
    patient_id: str = Field(min_length=1, max_length=128)


class CodingGapDetectRequest(_QuestionRequest):
    patient_id: str = Field(min_length=1, max_length=128)
    question: str = Field(
        default="Review coding and claims consistency gaps for this patient.",
        min_length=3,
    )


class CohortRiskSummaryRequest(_QuestionRequest):
    top_k: int = Field(default=5, ge=1)

    @field_validator("top_k")
    @classmethod
    def _top_k_within_limit(cls, value: int) -> int:
        if value > _limits.max_cohort_top_k:
            raise ValueError(f"top_k must be at most {_limits.max_cohort_top_k}")
        return value


class SkillsPlanRequest(_Request):
    business_goal: str = Field(min_length=3, max_length=128)
    agent: str | None = Field(default=None, min_length=1, max_length=128)
