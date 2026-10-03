"""Request contracts for the HTTP API and MCP tools.

Size limits come from settings, bound once by the composition root through
``configure_request_limits`` and read at validation time.
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
    def max_top_k(self) -> int:
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


def _max_top_k(value: int) -> int:
    if value > _limits.max_top_k:
        raise ValueError(f"top_k must be at most {_limits.max_top_k}")
    return value


# Reusable field types. Limits bound at runtime are enforced by AfterValidator so
# every model shares one implementation instead of per-class field validators.
Question = Annotated[str, Field(min_length=3), AfterValidator(_max_question_chars)]
EntityId = Annotated[str, Field(min_length=1, max_length=128)]
OptionalEntityId = Annotated[EntityId | None, Field(default=None)]
TopK = Annotated[int, Field(default=5, ge=1), AfterValidator(_max_top_k)]


class _QuestionRequest(_Request):
    question: Question


class QueryRequest(_QuestionRequest):
    entity_id: OptionalEntityId


class VectorEvidenceSearchRequest(_QuestionRequest):
    entity_id: OptionalEntityId
    top_k: TopK


class GraphRagAnswerRequest(_QuestionRequest):
    entity_id: OptionalEntityId
    response_style: Literal["concise", "operational", "audit"] = "concise"


class EntityRequest(_Request):
    entity_id: EntityId


class EvidenceBundleExportRequest(_QuestionRequest):
    entity_id: OptionalEntityId
    include_raw_payload: bool = False


class SkillsPlanRequest(_Request):
    business_goal: str = Field(min_length=3, max_length=128)
    agent: str | None = Field(default=None, min_length=1, max_length=128)
