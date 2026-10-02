"""Interfaces (ports) that domain services implement with concrete adapters.

Orchestration and agent code depend on these protocols, never on Qdrant,
Neo4j, a specific LLM SDK, Redis, or MLflow directly.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeVar, runtime_checkable

Record = dict[str, Any]
F = TypeVar("F", bound=Callable[..., Any])


@runtime_checkable
class VectorStore(Protocol):
    """Semantic search over embedded evidence, optionally scoped to one subject."""

    def search(self, query_text: str, *, scope_id: str | None, limit: int) -> list[Record]: ...


@runtime_checkable
class GraphStore(Protocol):
    """Relationship lookup for a set of entity identifiers."""

    def neighborhood(self, entity_ids: list[str]) -> list[Record]: ...


@runtime_checkable
class LLMProvider(Protocol):
    """Text generation behind a provider-neutral gateway."""

    def generate(self, *, prompt: str, timeout_seconds: int, max_tokens: int, temperature: float = 0.2) -> str: ...


@runtime_checkable
class SessionStore(Protocol):
    """Conversation memory keyed by session id."""

    def get_or_create(self, session_id: str) -> Any: ...

    def get(self, session_id: str) -> Any | None: ...

    def delete(self, session_id: str) -> None: ...

    def active_count(self) -> int: ...


@runtime_checkable
class Tracer(Protocol):
    """Span-style tracing for agent nodes, retrievers, and LLM calls."""

    def enabled(self) -> bool: ...

    def wrap(self, name: str, span_type: str, fn: F) -> F: ...


class NoopTracer:
    """Tracer used when no tracing backend is configured."""

    def enabled(self) -> bool:
        return False

    def wrap(self, name: str, span_type: str, fn: F) -> F:
        return fn
