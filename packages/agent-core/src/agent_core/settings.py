"""Typed base settings shared by agent services.

Domain services subclass ``AgentServiceSettings`` and add their own store and
model fields. Values come from environment variables.

Service settings use the ``AGENT_`` prefix. The legacy ``RAG_API_`` names are
still read during the ADR-0012 Phase 3b deprecation window; the new name wins
when both are set.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Annotated

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_PREFIX = "AGENT_"
LEGACY_ENV_PREFIX = "RAG_API_"

logger = logging.getLogger(__name__)
_warned_legacy_names: set[str] = set()


def env_alias(suffix: str) -> AliasChoices:
    """Read ``AGENT_<suffix>``, falling back to the deprecated ``RAG_API_<suffix>``."""
    return AliasChoices(f"{ENV_PREFIX}{suffix}", f"{LEGACY_ENV_PREFIX}{suffix}")


def legacy_env_names() -> list[str]:
    """Return the deprecated ``RAG_API_*`` variables set in the environment."""
    return sorted(name for name in os.environ if name.startswith(LEGACY_ENV_PREFIX))


class AgentServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    # LLM gateway
    llm_provider: str = Field(default="ollama", validation_alias="LLM_PROVIDER")
    llm_model: str = Field(default="llama3.1", validation_alias=AliasChoices("LLM_MODEL", "OLLAMA_MODEL"))
    llm_fallback_provider: str = Field(default="", validation_alias="LLM_FALLBACK_PROVIDER")
    llm_fallback_model: str = Field(default="", validation_alias="LLM_FALLBACK_MODEL")
    llm_timeout_seconds: int = Field(default=120, ge=1, validation_alias="LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(default=1200, ge=1, validation_alias="LLM_MAX_TOKENS")

    # Governance
    tool_policy_path: Path | None = Field(default=None, validation_alias=env_alias("TOOL_POLICY_PATH"))
    default_caller_role: str = Field(default="generation", validation_alias=env_alias("DEFAULT_CALLER_ROLE"))
    allow_role_header: bool = Field(default=True, validation_alias=env_alias("ALLOW_ROLE_HEADER"))
    audit_log_path: Path = Field(default=Path("logs/agent_audit.log"), validation_alias=env_alias("AUDIT_LOG_PATH"))
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"], validation_alias=env_alias("ALLOW_ORIGINS")
    )

    # Response budgets
    max_question_chars: int = Field(default=1000, ge=1, validation_alias=env_alias("MAX_QUESTION_CHARS"))
    max_context_items: int = Field(default=5, ge=1, validation_alias=env_alias("MAX_CONTEXT_ITEMS"))
    max_evidence_chars: int = Field(default=240, ge=1, validation_alias=env_alias("MAX_EVIDENCE_CHARS"))
    max_answer_chars: int = Field(default=2000, ge=1, validation_alias=env_alias("MAX_ANSWER_CHARS"))
    max_response_bytes: int = Field(default=50000, ge=1, validation_alias=env_alias("MAX_RESPONSE_BYTES"))

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or ["*"]
        return value

    @field_validator("audit_log_path", mode="after")
    @classmethod
    def _resolve_audit_path(cls, value: Path) -> Path:
        # Audit logs are runtime state: resolve against the working directory,
        # never the (read-only) installed package.
        return value if value.is_absolute() else Path.cwd() / value

    @model_validator(mode="after")
    def _warn_legacy_env(self) -> AgentServiceSettings:
        names = [name for name in legacy_env_names() if name not in _warned_legacy_names]
        if names:
            _warned_legacy_names.update(names)
            logger.warning(
                "Deprecated environment variables %s are set; rename them to the %s prefix",
                ", ".join(names),
                ENV_PREFIX,
            )
        return self
