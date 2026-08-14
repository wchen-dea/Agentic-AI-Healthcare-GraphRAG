from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FLINK_APP_DIR = REPO_ROOT / "flink-app"
if str(FLINK_APP_DIR) not in sys.path:
    sys.path.insert(0, str(FLINK_APP_DIR))


def _load_generator():
    module_path = REPO_ROOT / "scripts" / "generate_ontology_seed_cypher.py"
    spec = importlib.util.spec_from_file_location("generate_ontology_seed_cypher", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


load_ontology_bundle = _load_generator().load_ontology_bundle


def main() -> int:
    bundle = load_ontology_bundle()
    generated = _load_generator().build_seed_cypher(bundle)
    target = REPO_ROOT / "neo4j" / "generated_ontology_seeds.cypher"
    current = target.read_text(encoding="utf-8")
    if generated != current:
        print("generated ontology seed cypher is out of date:", target, file=sys.stderr)
        return 1

    bootstrap_result = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "test_neo4j_bootstrap.py")],
        cwd=REPO_ROOT,
        check=False,
    )
    if bootstrap_result.returncode != 0:
        return bootstrap_result.returncode

    patterns = [
        "test_ontology_loader.py",
        "test_runtime_rules.py",
        "test_storage.py",
        "test_graph_writes.py",
        "test_pipeline_service.py",
        "test_seed_generation.py",
    ]
    runner = unittest.TextTestRunner(verbosity=2)
    for pattern in patterns:
        suite = unittest.defaultTestLoader.discover(
            str(FLINK_APP_DIR / "tests"),
            pattern=pattern,
        )
        result = runner.run(suite)
        if not result.wasSuccessful():
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())