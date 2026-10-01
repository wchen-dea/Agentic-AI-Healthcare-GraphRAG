"""Typed settings for the supply-chain agent service.

Extends ``agent_core.settings.AgentServiceSettings`` with the supply-chain
stores, model gateway, and packaged config files (ADR-0012 Phase 4).
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


class SupplyChainAgentSettings(AgentServiceSettings):
    # Validate defaults so packaged config paths resolve even when unset.
    model_config = SettingsConfigDict(validate_default=True)

    # Retrieval stores
    qdrant_url: str = Field(default="http://localhost:6335", validation_alias="QDRANT_URL")
    qdrant_collection: str = Field(default="supplychain_events", validation_alias="QDRANT_COLLECTION")
    neo4j_uri: str = Field(default="bolt://localhost:7688", validation_alias="NEO4J_URI")
    neo4j_user: str = Field(default="neo4j", validation_alias="NEO4J_USER")
    # Local-development default only; deployments inject the real secret.
    neo4j_password: SecretStr = Field(default=SecretStr("supplychain123"), validation_alias="NEO4J_PASSWORD")
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", validation_alias="EMBEDDING_MODEL"
    )

    # Model gateway
    ollama_url: str = Field(default="http://ollama:11434", validation_alias="OLLAMA_URL")
    llm_timeout_seconds: int = Field(default=300, ge=1, validation_alias="LLM_TIMEOUT_SECONDS")

    # Tool surface
    mcp_server_name: str = Field(default="SupplyChainGraphRAG MCP", validation_alias="MCP_SERVER_NAME")
    skills_layer_path: Path | None = Field(default=None, validation_alias=env_name("SKILLS_LAYER_PATH"))

    # Observability
    mlflow_tracking_uri: str = Field(default="", validation_alias="MLFLOW_TRACKING_URI")

    @field_validator("tool_policy_path", mode="after")
    @classmethod
    def _resolve_tool_policy(cls, value: Path | None) -> Path:
        return _resolve_packaged(value, "tool_policies.json")

    @field_validator("skills_layer_path", mode="after")
    @classmethod
    def _resolve_skills_layer(cls, value: Path | None) -> Path:
        return _resolve_packaged(value, "skills_layer.json")


def load_settings() -> SupplyChainAgentSettings:
    """Read settings from the environment. Called once by the composition root."""
    return SupplyChainAgentSettings()
