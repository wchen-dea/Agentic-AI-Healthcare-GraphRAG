"""Request contracts for the HTTP API and MCP tools.

Size limits come from settings, bound once by the composition root through
``configure_request_limits`` and read at validation time.
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
    def max_top_k(self) -> int:
        return max(self.max_context_items, 8)


_limits = RequestLimits()


def configure_request_limits(limits: RequestLimits) -> None:
    global _limits
    _limits = limits


def request_limits() -> RequestLimits:
    return _limits


EntityId = Field(default=None, min_length=1, max_length=128)


class _Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _QuestionRequest(_Request):
    question: str = Field(min_length=3)

    @field_validator("question")
    @classmethod
    def _question_within_limit(cls, value: str) -> str:
        if len(value) > _limits.max_question_chars:
            raise ValueError(f"question must be at most {_limits.max_question_chars} characters")
        return value


class QueryRequest(_QuestionRequest):
    entity_id: str | None = EntityId


class VectorEvidenceSearchRequest(_QuestionRequest):
    entity_id: str | None = EntityId
    top_k: int = Field(default=5, ge=1)

    @field_validator("top_k")
    @classmethod
    def _top_k_within_limit(cls, value: int) -> int:
        if value > _limits.max_top_k:
            raise ValueError(f"top_k must be at most {_limits.max_top_k}")
        return value


class GraphRagAnswerRequest(_QuestionRequest):
    entity_id: str | None = EntityId
    response_style: Literal["concise", "operational", "audit"] = "concise"


class EntityRequest(_Request):
    entity_id: str = Field(min_length=1, max_length=128)


class EvidenceBundleExportRequest(_QuestionRequest):
    entity_id: str | None = EntityId
    include_raw_payload: bool = False


class SkillsPlanRequest(_Request):
    business_goal: str = Field(min_length=3, max_length=128)
    agent: str | None = Field(default=None, min_length=1, max_length=128)
