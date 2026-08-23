"""Ontology relationship cardinality conformance tests.

Validates that graph_writes.py Cypher patterns conform to the
cardinality constraints declared in relationships.yaml.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

import yaml

PLATFORM_DIR = Path(__file__).resolve().parents[4] / "platform" / "healthcare"
RELATIONSHIPS_FILE = PLATFORM_DIR / "ontology" / "relationships.yaml"
GRAPH_WRITES_FILE = PLATFORM_DIR / "flink-app" / "app" / "graph_writes.py"

sys.path.insert(0, str(PLATFORM_DIR / "flink-app"))


class RelationshipCardinalityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ontology = yaml.safe_load(RELATIONSHIPS_FILE.read_text())
        cls.relationships = {r["type"]: r for r in cls.ontology.get("relationships", [])}
        cls.graph_writes_source = GRAPH_WRITES_FILE.read_text()

    def test_all_ontology_relationships_exist(self):
        self.assertGreater(len(self.relationships), 0)

    def test_many_to_one_relationships_use_merge_not_create(self):
        """many:1 relationships should use MERGE to prevent duplicates."""
        many_to_one = [r["type"] for r in self.relationships.values() if r.get("cardinality") == "many:1"]
        for rel_type in many_to_one:
            if rel_type in self.graph_writes_source:
                self.assertNotIn(
                    f"CREATE ({{}})-[:{rel_type}]",
                    self.graph_writes_source,
                    f"{rel_type} is many:1 but uses CREATE instead of MERGE",
                )

    def test_required_properties_present_in_cypher(self):
        """Relationships with required properties should set them in Cypher (if written by graph_writes)."""
        # Seed-only relationships are in generated_ontology_seeds.cypher, not graph_writes
        seed_only_rels = {"HAS_KNOWN_REACTION", "CONTRAINDICATED_FOR", "INTERACTS_WITH"}
        for rel_type, spec in self.relationships.items():
            required = spec.get("required_properties", [])
            if not required or rel_type not in self.graph_writes_source or rel_type in seed_only_rels:
                continue
            for prop in required:
                pattern = re.compile(rf"\[.*:{rel_type}\s*\{{.*{prop}.*\}}", re.DOTALL)
                alt_pattern = re.compile(rf":{rel_type}\s*\{{.*{prop}", re.DOTALL)
                has_prop = pattern.search(self.graph_writes_source) or alt_pattern.search(self.graph_writes_source)
                if not has_prop:
                    set_pattern = re.compile(rf"SET\s+\w+\.{prop}", re.DOTALL)
                    has_prop = set_pattern.search(self.graph_writes_source)
                self.assertTrue(
                    has_prop,
                    f"{rel_type} requires property '{prop}' but it's not set in graph_writes.py",
                )

    def test_node_types_match_ontology(self):
        """Node labels used in graph_writes should match ontology entity types."""
        entities_file = PLATFORM_DIR / "ontology" / "entities.yaml"
        entities = yaml.safe_load(entities_file.read_text())
        declared_types = {e["canonical_name"] for e in entities.get("entities", [])}
        merge_labels = set(re.findall(r"MERGE\s*\(\w+:(\w+)", self.graph_writes_source))
        merge_labels -= {"Patient", "ClinicalEvent"}  # always present
        for label in merge_labels:
            self.assertIn(
                label, declared_types,
                f"graph_writes uses label '{label}' not declared in entities.yaml",
            )

    def test_relationship_directions_match_ontology(self):
        """Relationships in graph_writes should go from→to as declared in ontology."""
        for rel_type, spec in self.relationships.items():
            if rel_type not in self.graph_writes_source:
                continue
            from_type = spec["from"]
            to_type = spec["to"]
            forward = re.search(rf"\({from_type.lower()}\w*:{from_type}\).*\[.*:{rel_type}", self.graph_writes_source, re.DOTALL)
            if not forward:
                forward = re.search(rf":{from_type}\).*\[.*:{rel_type}", self.graph_writes_source, re.DOTALL)
            reverse_wrong = re.search(rf"\(\w+:{to_type}\)-\[.*:{rel_type}\]->.*:{from_type}", self.graph_writes_source)
            if reverse_wrong:
                self.fail(f"{rel_type} direction is reversed: should be {from_type}->{to_type}")

    def test_graph_search_query_uses_declared_relationships(self):
        """Retrieval Cypher should only traverse ontology-declared relationships."""
        retrieval_file = Path(__file__).resolve().parents[1] / "domain" / "retrieval.py"
        retrieval_source = retrieval_file.read_text()
        used_rels = set(re.findall(r"\[:([A-Z_]{3,})\]", retrieval_source))
        used_rels |= set(re.findall(r"-\[:([A-Z_]{3,})\]-", retrieval_source))
        for rel in used_rels:
            self.assertIn(
                rel, self.relationships,
                f"retrieval.py uses relationship '{rel}' not declared in relationships.yaml",
            )


if __name__ == "__main__":
    unittest.main()
