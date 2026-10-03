import importlib
import sys
import types
from pathlib import Path

import pytest

JOB_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(JOB_DIR))


def _stub_kafka(monkeypatch):
    names = {
        "confluent_kafka": {"Consumer": object, "KafkaException": Exception},
        "confluent_kafka.schema_registry": {"SchemaRegistryClient": object},
        "confluent_kafka.schema_registry.avro": {"AvroDeserializer": object},
        "confluent_kafka.serialization": {
            "MessageField": object,
            "SerializationContext": object,
        },
    }
    for name, attrs in names.items():
        module = types.ModuleType(name)
        for attr, value in attrs.items():
            setattr(module, attr, value)
        monkeypatch.setitem(sys.modules, name, module)


def _load_job(monkeypatch, *, without_knowledge_core: bool):
    _stub_kafka(monkeypatch)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("EMBEDDING_DIM", raising=False)
    if without_knowledge_core:
        monkeypatch.setitem(sys.modules, "knowledge_core", None)
        monkeypatch.setitem(sys.modules, "knowledge_core.embedding", None)
    sys.modules.pop("supplychain_graph_rag_job", None)
    return importlib.import_module("supplychain_graph_rag_job")


@pytest.mark.parametrize("without_knowledge_core", [True, False])
def test_job_imports_and_embeds(monkeypatch, without_knowledge_core):
    if not without_knowledge_core:
        pytest.importorskip("knowledge_core.embedding")
    job = _load_job(monkeypatch, without_knowledge_core=without_knowledge_core)

    vec = job._embed("supplier delay at plant A")

    assert len(vec) == job.VECTOR_SIZE == 384
    assert abs(sum(x * x for x in vec) ** 0.5 - 1.0) < 1e-6


def test_fallback_matches_knowledge_core(monkeypatch):
    kc = pytest.importorskip("knowledge_core.embedding")
    job = _load_job(monkeypatch, without_knowledge_core=True)

    assert job._md5_embedding("late shipment") == kc._md5_embedding("late shipment")


def test_embed_survives_model_failure(monkeypatch):
    job = _load_job(monkeypatch, without_knowledge_core=True)

    def boom(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(job, "stable_embedding", boom)

    assert job._embed("quality hold") == job._md5_embedding("quality hold")


def test_strict_mode_embed_raises_instead_of_md5(monkeypatch):
    job = _load_job(monkeypatch, without_knowledge_core=True)
    monkeypatch.setenv("EMBEDDING_REQUIRE_MODEL", "true")

    def boom(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(job, "stable_embedding", boom)

    with pytest.raises(RuntimeError, match="model unavailable"):
        job._embed("quality hold")


def test_strict_mode_requires_knowledge_core(monkeypatch):
    monkeypatch.setenv("EMBEDDING_REQUIRE_MODEL", "true")

    with pytest.raises(ImportError):
        _load_job(monkeypatch, without_knowledge_core=True)


def test_job_uses_shared_embedding(monkeypatch):
    kc = pytest.importorskip("knowledge_core.embedding")
    monkeypatch.delenv("EMBEDDING_REQUIRE_MODEL", raising=False)
    job = _load_job(monkeypatch, without_knowledge_core=False)

    assert job.stable_embedding is kc.stable_embedding
    assert job.VECTOR_SIZE == kc.VECTOR_SIZE


def test_fallback_vector_size_follows_provider(monkeypatch):
    monkeypatch.setitem(sys.modules, "knowledge_core", None)
    monkeypatch.setitem(sys.modules, "knowledge_core.embedding", None)
    _stub_kafka(monkeypatch)
    monkeypatch.delenv("EMBEDDING_REQUIRE_MODEL", raising=False)
    monkeypatch.setenv("EMBEDDING_PROVIDER", "databricks")
    monkeypatch.delenv("EMBEDDING_DIM", raising=False)
    sys.modules.pop("supplychain_graph_rag_job", None)
    job = importlib.import_module("supplychain_graph_rag_job")

    assert job.VECTOR_SIZE == 1024
    assert len(job._embed("supplier delay")) == 1024

    monkeypatch.setenv("EMBEDDING_DIM", "768")
    sys.modules.pop("supplychain_graph_rag_job", None)
    job = importlib.import_module("supplychain_graph_rag_job")
    assert job.VECTOR_SIZE == 768
