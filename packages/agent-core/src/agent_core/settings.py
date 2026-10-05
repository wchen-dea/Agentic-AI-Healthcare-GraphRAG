"""Typed base settings shared by agent services.

Domain services subclass ``AgentServiceSettings`` and add their own store and
model fields. Values come from environment variables.

Service settings use the ``AGENT_`` prefix (ADR-0012). The legacy ``RAG_API_``
names were removed in Phase 4 and are ignored. ``LLM_MODEL`` is the only model
variable; provider-specific aliases (``OLLAMA_MODEL``, ``DATABRICKS_MODEL``) are
not read.
"""
from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

ENV_PREFIX = "AGENT_"


def env_name(suffix: str) -> str:
    """Return the environment variable name for a service setting."""
    return f"{ENV_PREFIX}{suffix}"


class AgentServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", frozen=True, populate_by_name=True)

    # LLM gateway
    llm_provider: str = Field(default="databricks", validation_alias="LLM_PROVIDER")
    llm_model: str = Field(default="databricks-gpt-5-6-luna", validation_alias="LLM_MODEL")
    llm_fallback_provider: str = Field(default="", validation_alias="LLM_FALLBACK_PROVIDER")
    llm_fallback_model: str = Field(default="", validation_alias="LLM_FALLBACK_MODEL")
    llm_timeout_seconds: int = Field(default=120, ge=1, validation_alias="LLM_TIMEOUT_SECONDS")
    llm_max_tokens: int = Field(default=1200, ge=1, validation_alias="LLM_MAX_TOKENS")

    # Governance
    tool_policy_path: Path | None = Field(default=None, validation_alias=env_name("TOOL_POLICY_PATH"))
    default_caller_role: str = Field(default="generation", validation_alias=env_name("DEFAULT_CALLER_ROLE"))
    allow_role_header: bool = Field(default=True, validation_alias=env_name("ALLOW_ROLE_HEADER"))
    audit_log_path: Path = Field(default=Path("logs/agent_audit.log"), validation_alias=env_name("AUDIT_LOG_PATH"))
    audit_fail_closed: bool = Field(default=False, validation_alias=env_name("AUDIT_FAIL_CLOSED"))
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["*"], validation_alias=env_name("ALLOW_ORIGINS")
    )

    # Response budgets
    max_question_chars: int = Field(default=1000, ge=1, validation_alias=env_name("MAX_QUESTION_CHARS"))
    max_context_items: int = Field(default=5, ge=1, validation_alias=env_name("MAX_CONTEXT_ITEMS"))
    max_evidence_chars: int = Field(default=240, ge=1, validation_alias=env_name("MAX_EVIDENCE_CHARS"))
    max_answer_chars: int = Field(default=2000, ge=1, validation_alias=env_name("MAX_ANSWER_CHARS"))
    max_response_bytes: int = Field(default=50000, ge=1, validation_alias=env_name("MAX_RESPONSE_BYTES"))

    # MCP server (used by agent_core.mcp_server; needs the ``mcp`` extra)
    mcp_instructions: str = Field(default="", validation_alias="MCP_INSTRUCTIONS")
    mcp_stateless_http: bool = Field(default=False, validation_alias="MCP_STATELESS_HTTP")
    mcp_json_response: bool = Field(default=False, validation_alias="MCP_JSON_RESPONSE")
    mcp_auth_required: bool = Field(default=False, validation_alias="MCP_AUTH_REQUIRED")
    mcp_auth_token: SecretStr = Field(default=SecretStr(""), validation_alias="MCP_AUTH_TOKEN")
    mcp_dns_rebinding_protection: bool = Field(default=False, validation_alias="MCP_DNS_REBINDING_PROTECTION")
    mcp_allowed_hosts: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="MCP_ALLOWED_HOSTS"
    )
    mcp_allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="MCP_ALLOWED_ORIGINS"
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            items = [item.strip() for item in value.split(",") if item.strip()]
            return items or ["*"]
        return value

    @field_validator("mcp_allowed_hosts", "mcp_allowed_origins", mode="before")
    @classmethod
    def _split_optional_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("audit_log_path", mode="after")
    @classmethod
    def _resolve_audit_path(cls, value: Path) -> Path:
        # Audit logs are runtime state: resolve against the working directory,
        # never the (read-only) installed package.
        return value if value.is_absolute() else Path.cwd() / value
