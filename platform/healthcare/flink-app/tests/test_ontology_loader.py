from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from helpers import REPO_ROOT, load_ontology_bundle


class OntologyLoaderTests(unittest.TestCase):
    def test_duplicate_entity_ids_fail_fast(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            shutil.copytree(REPO_ROOT / "config" / "ontology", tmp_path / "ontology")
            entities_path = tmp_path / "ontology" / "entities.yaml"
            entities_path.write_text(
                entities_path.read_text(encoding="utf-8") + "\n- id: patient\n  canonical_name: PatientDup\n",
                encoding="utf-8",
            )
            load_ontology_bundle.cache_clear()
            with self.assertRaisesRegex(ValueError, "Duplicate entity id 'patient'"):
                load_ontology_bundle(str(tmp_path / "ontology"))

    def test_malformed_rule_pack_fails_fast(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            shutil.copytree(REPO_ROOT / "config" / "ontology", tmp_path / "ontology")
            rule_path = tmp_path / "ontology" / "rules" / "lab_signals.yaml"
            rule_path.write_text("rules: [invalid", encoding="utf-8")
            load_ontology_bundle.cache_clear()
            with self.assertRaises(Exception):
                load_ontology_bundle(str(tmp_path / "ontology"))

    def test_relationship_outputs_reference_known_types(self):
        bundle = load_ontology_bundle()
        rule_types = bundle["relationship_types"]
        for rule in bundle["rule_packs"]["lab_signals"]["rules"]:
            self.assertIn(rule["output_edge"]["type"], rule_types)
        for rule in bundle["rule_packs"]["claims_outcomes"]["rules"]:
            self.assertIn(rule["output_edge"]["type"], rule_types)

    def test_split_mapping_files_are_merged_into_bundle(self):
        bundle = load_ontology_bundle()
        local_mappings = bundle["vocabularies"]["local_mappings"]
        self.assertIn("patient_risk_tiers", local_mappings)
        self.assertIn("patient_sex", local_mappings)
        self.assertIn("medication_drug_classes", local_mappings)
        self.assertIn("medication_safety_tiers", local_mappings)
        self.assertIn("provider_specialties", local_mappings)
        self.assertIn("device_types", local_mappings)
        self.assertIn("payer_plan_types", local_mappings)
        self.assertIn("payer_network_tiers", local_mappings)
