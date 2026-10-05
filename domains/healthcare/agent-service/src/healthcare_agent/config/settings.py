"""Typed settings for the healthcare agent service.

Extends ``agent_core.settings.AgentServiceSettings`` with the healthcare stores,
model tiers, and packaged config files. Environment variable names are an
operations contract and stay stable across refactors (ADR-0012).
"""
from __future__ import annotations

from pathlib import Path

from agent_core.settings import AgentServiceSettings, env_name
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PACKAGE_ROOT / "config"


def _resolve_packaged(value: Path | None, default_name: str) -> Path:
    if value is None:
        return CONFIG_DIR / default_name
    return value if value.is_absolute() else PACKAGE_ROOT / value


class HealthcareAgentSettings(AgentServiceSettings):
    # Validate defaults so packaged config paths resolve even when unset.
    model_config = SettingsConfigDict(validate_default=True)

    # Retrieval stores
    qdrant_url: str = Field(default="http://qdrant:6333", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(default="healthcare_events", validation_alias="QDRANT_COLLECTION")
    neo4j_uri: str = Field(default="bolt://neo4j:7687", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    # Local-development default only; deployments inject the real secret.
    neo4j_password: SecretStr = Field(default=SecretStr("healthcare123"), validation_alias="NEO4J_PASSWORD")

    # Model gateway
    ollama_url: str = Field(default="http://ollama:11434", validation_alias="OLLAMA_URL")
    llm_model_simple: str = Field(default="", validation_alias="LLM_MODEL_SIMPLE")
    llm_model_moderate: str = Field(default="", validation_alias="LLM_MODEL_MODERATE")
    llm_model_complex: str = Field(default="", validation_alias="LLM_MODEL_COMPLEX")
    llm_latency_target_ms: float = Field(default=0.0, ge=0, validation_alias="LLM_LATENCY_TARGET_MS")
    llm_cost_budget_hourly_usd: float = Field(default=0.0, ge=0, validation_alias="LLM_COST_BUDGET_HOURLY_USD")

    # Tool surface
    mcp_server_name: str = Field(default="HealthcareGraphRAG MCP", validation_alias="MCP_SERVER_NAME")
    skills_layer_path: Path | None = Field(default=None, validation_alias=env_name("SKILLS_LAYER_PATH"))

    # Durable patient memory
    patient_memory_store_backend: str = Field(
        default="memory", validation_alias="PATIENT_MEMORY_STORE_BACKEND"
    )
    patient_memory_retention_seconds: int = Field(
        default=30 * 24 * 60 * 60,
        ge=0,
        validation_alias="PATIENT_MEMORY_RETENTION_SECONDS",
    )
    patient_memory_max_facts: int = Field(
        default=100, ge=1, validation_alias="PATIENT_MEMORY_MAX_FACTS"
    )
    patient_memory_consent_required: bool = Field(
        default=True, validation_alias="PATIENT_MEMORY_CONSENT_REQUIRED"
    )

    # Observability
    mlflow_tracking_uri: str = Field(default="", validation_alias="MLFLOW_TRACKING_URI")

    # LangGraph durable execution
    langgraph_checkpoint_postgres_uri: str = Field(
        default="", validation_alias="LANGGRAPH_CHECKPOINT_POSTGRES_URI"
    )
    langgraph_checkpoint_required: bool = Field(
        default=False, validation_alias="LANGGRAPH_CHECKPOINT_REQUIRED"
    )

    @field_validator("patient_memory_store_backend")
    @classmethod
    def _validate_patient_memory_backend(cls, value: str) -> str:
        backend = value.strip().lower()
        if backend not in {"memory", "redis", "postgres"}:
            raise ValueError(
                "PATIENT_MEMORY_STORE_BACKEND must be 'memory', 'redis', or 'postgres'"
            )
        return backend

    @field_validator("tool_policy_path", mode="after")
    @classmethod
    def _resolve_tool_policy(cls, value: Path | None) -> Path:
        return _resolve_packaged(value, "tool_policies.json")

    @field_validator("skills_layer_path", mode="after")
    @classmethod
    def _resolve_skills_layer(cls, value: Path | None) -> Path:
        return _resolve_packaged(value, "skills_layer.json")


def load_settings() -> HealthcareAgentSettings:
    """Read settings from the environment. Called once by the composition root."""
    return HealthcareAgentSettings()
