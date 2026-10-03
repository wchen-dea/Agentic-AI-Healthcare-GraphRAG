import pytest

from supply_chain_agent.retrieval import embedding


def test_fallback_when_model_missing_and_not_strict(monkeypatch):
    monkeypatch.delenv("EMBEDDING_REQUIRE_MODEL", raising=False)
    monkeypatch.setattr(embedding, "_load_model", lambda _name: None)

    vec = embedding.stable_embedding("late shipment")

    assert len(vec) == embedding.VECTOR_SIZE
    assert vec == embedding._md5_embedding("late shipment", embedding.VECTOR_SIZE)


def test_strict_mode_refuses_md5_fallback(monkeypatch):
    monkeypatch.setenv("EMBEDDING_REQUIRE_MODEL", "true")
    monkeypatch.setattr(embedding, "_load_model", lambda _name: None)

    with pytest.raises(RuntimeError, match="EMBEDDING_REQUIRE_MODEL"):
        embedding.stable_embedding("late shipment")


def test_query_embedding_matches_ingest_settings():
    kc = pytest.importorskip("knowledge_core.embedding")

    assert embedding.DEFAULT_MODEL == kc.DEFAULT_MODEL
    assert embedding.VECTOR_SIZE == kc.VECTOR_SIZE
    assert embedding._md5_embedding("late shipment", kc.VECTOR_SIZE) == kc._md5_embedding("late shipment")


class _FakeResponse:
    def __init__(self, payload):
        import json

        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


@pytest.fixture
def databricks_env(monkeypatch):
    for name in ("EMBEDDING_DIM", "EMBEDDING_REQUIRE_MODEL", "DATABRICKS_EMBEDDING_ENDPOINT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "databricks")
    monkeypatch.setenv("DATABRICKS_HOST", "example.cloud.databricks.com")
    monkeypatch.setenv("DATABRICKS_TOKEN", "dapi-test-secret")
    embedding._databricks_embed_cached.cache_clear()
    yield
    embedding._databricks_embed_cached.cache_clear()


def test_provider_defaults(monkeypatch):
    monkeypatch.delenv("EMBEDDING_DIM", raising=False)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    assert embedding.get_provider() == "local"
    assert embedding.get_vector_size() == 384
    monkeypatch.setenv("EMBEDDING_PROVIDER", "databricks")
    assert embedding.get_vector_size() == 1024
    monkeypatch.setenv("EMBEDDING_DIM", "768")
    assert embedding.get_vector_size() == 768
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    with pytest.raises(ValueError):
        embedding.get_provider()


def test_databricks_provider_calls_endpoint_and_caches(databricks_env, monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        return _FakeResponse({"data": [{"embedding": [3.0, 4.0] + [0.0] * 1022}]})

    monkeypatch.setattr(embedding.urllib.request, "urlopen", fake_urlopen)

    vec = embedding.stable_embedding("late shipment")
    again = embedding.stable_embedding("late shipment")

    assert len(calls) == 1
    assert calls[0].full_url == (
        "https://example.cloud.databricks.com/serving-endpoints/databricks-gte-large-en/invocations"
    )
    assert calls[0].get_header("Authorization") == "Bearer dapi-test-secret"
    assert vec == again
    assert len(vec) == 1024
    assert vec[:2] == pytest.approx([0.6, 0.8])


def test_databricks_strict_error_does_not_leak_token(databricks_env, monkeypatch):
    import urllib.error

    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(embedding.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("EMBEDDING_REQUIRE_MODEL", "true")

    with pytest.raises(RuntimeError, match="HTTP 401") as info:
        embedding.stable_embedding("late shipment")
    assert "dapi-test-secret" not in str(info.value)
    assert info.value.__cause__ is None


def test_databricks_failure_falls_back_when_not_strict(databricks_env, monkeypatch):
    def fake_urlopen(request, timeout):
        raise OSError("connection refused")

    monkeypatch.setattr(embedding.urllib.request, "urlopen", fake_urlopen)

    assert embedding.stable_embedding("late shipment") == embedding._md5_embedding("late shipment", 1024)


def test_provider_settings_match_ingest():
    kc = pytest.importorskip("knowledge_core.embedding")

    assert embedding.PROVIDER_DEFAULT_DIMS == kc.PROVIDER_DEFAULT_DIMS
    assert embedding.DEFAULT_DATABRICKS_ENDPOINT == kc.DEFAULT_DATABRICKS_ENDPOINT
