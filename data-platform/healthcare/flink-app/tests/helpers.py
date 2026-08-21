from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
FLINK_APP_DIR = REPO_ROOT / "flink-app"
if str(FLINK_APP_DIR) not in sys.path:
    sys.path.insert(0, str(FLINK_APP_DIR))


from app.ontology_loader import load_claims_outcome_rules, load_lab_signal_rules, load_ontology_bundle  # noqa: E402
from app.normalization import normalize_event_payload  # noqa: E402
from app.rules_engine import evaluate_claims_outcome_rules, evaluate_lab_signal_rules  # noqa: E402


def load_seed_generator():
    module_path = REPO_ROOT / "scripts" / "generate_ontology_seed_cypher.py"
    spec = importlib.util.spec_from_file_location("generate_ontology_seed_cypher", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_seed_cypher = load_seed_generator().build_seed_cypher


def load_processor_module():
    confluent_kafka = types.ModuleType("confluent_kafka")
    confluent_kafka.Consumer = object
    confluent_kafka.KafkaException = Exception

    schema_registry = types.ModuleType("confluent_kafka.schema_registry")
    schema_registry.SchemaRegistryClient = object

    schema_registry_avro = types.ModuleType("confluent_kafka.schema_registry.avro")
    schema_registry_avro.AvroDeserializer = object

    serialization = types.ModuleType("confluent_kafka.serialization")
    serialization.MessageField = types.SimpleNamespace(VALUE="value")
    serialization.SerializationContext = object

    neo4j = types.ModuleType("neo4j")
    neo4j.GraphDatabase = types.SimpleNamespace(driver=lambda *args, **kwargs: None)

    qdrant_client = types.ModuleType("qdrant_client")
    qdrant_client.QdrantClient = object

    qdrant_models = types.ModuleType("qdrant_client.models")
    qdrant_models.Distance = types.SimpleNamespace(COSINE="cosine")
    qdrant_models.PointStruct = object
    qdrant_models.VectorParams = object

    stub_modules = {
        "confluent_kafka": confluent_kafka,
        "confluent_kafka.schema_registry": schema_registry,
        "confluent_kafka.schema_registry.avro": schema_registry_avro,
        "confluent_kafka.serialization": serialization,
        "neo4j": neo4j,
        "qdrant_client": qdrant_client,
        "qdrant_client.models": qdrant_models,
    }
    original_modules = {name: sys.modules.get(name) for name in stub_modules}

    try:
        sys.modules.update(stub_modules)
        module_path = FLINK_APP_DIR / "healthcare_graph_rag_job.py"
        spec = importlib.util.spec_from_file_location("healthcare_graph_rag_job_test", module_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in original_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original