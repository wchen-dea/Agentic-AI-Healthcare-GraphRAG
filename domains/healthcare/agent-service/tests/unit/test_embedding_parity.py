"""Ingest (Flink) and query (agent) share knowledge_core.embedding."""
import pytest

from knowledge_core import embedding


def test_fallback_when_model_missing_and_not_strict(monkeypatch):
    monkeypatch.delenv("EMBEDDING_REQUIRE_MODEL", raising=False)
    monkeypatch.setattr(embedding, "_load_model", lambda _name: False)

    assert embedding.stable_embedding("chest pain") == embedding._md5_embedding("chest pain")


def test_strict_mode_refuses_md5_fallback(monkeypatch):
    monkeypatch.setenv("EMBEDDING_REQUIRE_MODEL", "true")
    monkeypatch.setattr(embedding, "_load_model", lambda _name: False)

    with pytest.raises(RuntimeError, match="EMBEDDING_REQUIRE_MODEL"):
        embedding.stable_embedding("chest pain")


def test_all_domains_resolve_to_a_model():
    assert set(embedding.DOMAIN_MODEL_NAMES) == set(embedding.ALL_DOMAINS)
    assert all(embedding.DOMAIN_MODEL_NAMES.values())
