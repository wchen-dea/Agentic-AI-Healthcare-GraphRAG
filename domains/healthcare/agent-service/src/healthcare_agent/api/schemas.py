"""Request contracts for the HTTP API and MCP tools.

Size limits come from settings, which the composition root binds once with
``configure_request_limits``. Validators read the bound limits at validation
time, so the models stay static and importable without a settings instance.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


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


class _Request(BaseModel):
    """Base for inbound contracts: unknown fields are rejected and strings trimmed."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


def _max_question_chars(value: str) -> str:
    if len(value) > _limits.max_question_chars:
        raise ValueError(f"question must be at most {_limits.max_question_chars} characters")
    return value


def _max_context_items(value: int) -> int:
    if value > _limits.max_context_items:
        raise ValueError(f"top_k must be at most {_limits.max_context_items}")
    return value


def _max_cohort_top_k(value: int) -> int:
    if value > _limits.max_cohort_top_k:
        raise ValueError(f"top_k must be at most {_limits.max_cohort_top_k}")
    return value


# Reusable field types. Limits bound at runtime are enforced by AfterValidator so
# every model shares one implementation instead of per-class field validators.
Question = Annotated[str, Field(min_length=3), AfterValidator(_max_question_chars)]
PatientId = Annotated[str, Field(min_length=1, max_length=128)]
OptionalPatientId = Annotated[PatientId | None, Field(default=None)]
TopK = Annotated[int, Field(default=5, ge=1), AfterValidator(_max_context_items)]
CohortTopK = Annotated[int, Field(default=5, ge=1), AfterValidator(_max_cohort_top_k)]
TimeWindowHours = Annotated[int, Field(ge=1, le=720)]


class _QuestionRequest(_Request):
    question: Question


class QueryRequest(_QuestionRequest):
    patient_id: OptionalPatientId
    structured: bool = Field(default=False, description="Return structured JSON response")
    session_id: str | None = Field(default=None, max_length=64)
    top_k: TopK


class PatientContextGetRequest(_Request):
    patient_id: PatientId
    include_claims: bool = True
    include_interactions: bool = True


class VectorEvidenceSearchRequest(_QuestionRequest):
    patient_id: OptionalPatientId
    top_k: TopK


class GraphRagAnswerRequest(_QuestionRequest):
    patient_id: OptionalPatientId
    response_style: Literal["concise", "clinical", "audit"] = "concise"


class RiskSummaryRequest(_Request):
    patient_id: PatientId
    time_window_hours: TimeWindowHours = 72


class EvidenceBundleExportRequest(_QuestionRequest):
    patient_id: OptionalPatientId
    include_raw_payload: bool = False


class TimelineExplainRequest(_Request):
    patient_id: PatientId
    time_window_hours: TimeWindowHours = 168


class MedicationRiskAssessRequest(_Request):
    patient_id: PatientId


class CodingGapDetectRequest(_Request):
    patient_id: PatientId
    question: Question = "Review coding and claims consistency gaps for this patient."


class CohortRiskSummaryRequest(_QuestionRequest):
    top_k: CohortTopK


class SkillsPlanRequest(_Request):
    business_goal: str = Field(min_length=3, max_length=128)
    agent: str | None = Field(default=None, min_length=1, max_length=128)
