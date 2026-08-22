from __future__ import annotations

import re
import unittest

from helpers import REPO_ROOT, build_seed_cypher, load_ontology_bundle


class SeedGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_ontology_bundle()
        cls.cypher = (REPO_ROOT / "neo4j" / "init.cypher").read_text(encoding="utf-8")
        cls.generated_path = REPO_ROOT / "neo4j" / "generated_ontology_seeds.cypher"
        cls.generated = cls.generated_path.read_text(encoding="utf-8")
        cls.drug_safety = cls.bundle["rule_packs"]["drug_safety"]
        cls.graph_seeds = cls.bundle["graph_seeds"]
        cls.compose = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    def test_claims_rules_align_with_seeded_outcomes(self):
        outcome_codes = {item["code"] for item in self.drug_safety["adverse_outcomes"]}
        for rule in self.bundle["rule_packs"]["claims_outcomes"]["rules"]:
            self.assertIn(rule["output_edge"]["adverse_outcome"], outcome_codes)

    def test_adverse_outcomes_match_seed_inventory(self):
        for outcome in self.drug_safety["adverse_outcomes"]:
            snippet = f'MERGE (:AdverseOutcome {{code: "{outcome["code"]}", description: "{outcome["description"]}"}});'
            self.assertIn(snippet, self.generated)

    def test_generated_seed_cypher_is_in_sync(self):
        self.assertEqual(build_seed_cypher(self.bundle), self.generated)

    def test_generated_seed_contains_condition_and_symptom_seeds(self):
        for condition_name in self.graph_seeds["condition_seeds"]:
            self.assertIn(f'MERGE (:Condition {{name: "{condition_name}"}});', self.generated)
        for symptom_name in self.graph_seeds["symptom_seeds"]:
            self.assertIn(f'MERGE (:Symptom {{name: "{symptom_name}"}});', self.generated)

    def test_generated_seed_contains_medication_metadata(self):
        for item in self.graph_seeds["medication_metadata"]:
            bool_text = "true" if item["is_validated_trade_name_used"] else "false"
            self.assertIn(
                f'MATCH (m:Medication {{name: "{item["name"]}"}}) SET m.activeIngredient = "{item["active_ingredient"]}", m.isValidatedTradeNameUsed = {bool_text};',
                self.generated,
            )

    def test_init_cypher_documents_generated_sections(self):
        self.assertIn("generated_ontology_seeds.cypher", self.cypher)

    def test_compose_uses_generated_seed_artifact(self):
        self.assertIn("generated_ontology_seeds.cypher", self.compose)
        self.assertIn("/bootstrap.sh", self.compose)

    def test_bootstrap_script_is_used_for_seeding(self):
        bootstrap = (REPO_ROOT / "neo4j" / "bootstrap.sh").read_text(encoding="utf-8")
        self.assertIn("NEO4J_GENERATED_SEEDS_FILE", bootstrap)
        self.assertIn("NEO4J_BOOTSTRAP_OUTPUT", bootstrap)

    def test_interactions_match_seed_inventory(self):
        for item in self.drug_safety["interactions"]:
            pattern = re.compile(
                rf'MATCH \(from:Medication \{{name: "{re.escape(item["from"])}"\}}\) '
                rf'MATCH \(to:Medication \{{name: "{re.escape(item["to"])}"\}}\) '
                rf'MERGE \(from\)-\[:INTERACTS_WITH \{{risk: "{re.escape(item["risk"])}", severity: "{re.escape(item["severity"])}", mechanism: "{re.escape(item["mechanism"])}"\}}\]->\(to\);',
            )
            self.assertRegex(self.generated, pattern)
            if item.get("mechanism"):
                self.assertIn(item["mechanism"], self.generated)

    def test_known_reactions_match_seed_inventory(self):
        for item in self.drug_safety["known_reactions"]:
            pattern = re.compile(
                rf'MATCH \(m:Medication \{{name: "{re.escape(item["medication"])}"\}}\) '
                rf'MATCH \(s:Symptom \{{name: "{re.escape(item["symptom"])}"\}}\) '
                rf'MERGE \(m\)-\[:HAS_KNOWN_REACTION \{{severity: "{re.escape(item["severity"])}", meddra_term: "{re.escape(item["meddra_term"])}"\}}\]->\(s\);',
            )
            self.assertRegex(self.generated, pattern)

    def test_contraindications_match_seed_inventory(self):
        for item in self.drug_safety["contraindications"]:
            pattern = re.compile(
                rf'MATCH \(m:Medication \{{name: "{re.escape(item["medication"])}"\}}\) '
                rf'MATCH \(c:Condition \{{name: "{re.escape(item["condition"])}"\}}\) '
                rf'MERGE \(m\)-\[:CONTRAINDICATED_FOR \{{reason: "{re.escape(item["reason"])}", severity: "{re.escape(item["severity"])}"\}}\]->\(c\);',
            )
            self.assertRegex(self.generated, pattern)

    def test_init_cypher_no_longer_duplicates_generated_interactions(self):
        self.assertNotIn('MERGE (w:Medication {name: "Warfarin"})', self.cypher)
        self.assertNotIn('SET r.mechanism = "CYP3A4_inhibition_increases_warfarin_exposure"', self.cypher)

    def test_init_cypher_no_longer_duplicates_generated_contraindications(self):
        self.assertNotIn('MERGE (war2:Medication {name: "Warfarin"})', self.cypher)
        self.assertNotIn('MERGE (met3)-[:CONTRAINDICATED_FOR {reason: "beta_blockade_induces_bronchospasm", severity: "high"}]->(cas);', self.cypher)

    def test_init_cypher_no_longer_duplicates_generated_known_reactions(self):
        self.assertNotIn('MERGE (war)-[:HAS_KNOWN_REACTION {severity: "high",   meddra_term: "Palpitation"}]->(sp1)', self.cypher)
        self.assertNotIn('MERGE (dex2)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Weight Decreased"}]->(swl3);', self.cypher)

    def test_init_cypher_no_longer_duplicates_generated_adverse_outcomes(self):
        self.assertNotIn('MERGE (:AdverseOutcome {code: "DE", description: "Death"});', self.cypher)
        self.assertNotIn('MERGE (:AdverseOutcome {code: "OT", description: "Other Serious (Important Medical Events)"});', self.cypher)

    def test_init_cypher_contains_no_seed_merge_statements(self):
        forbidden_patterns = [
            r"MERGE \(:AdverseOutcome \{",
            r"MERGE \(:Condition \{",
            r"MERGE \(:Symptom \{",
            r"INTERACTS_WITH",
            r"CONTRAINDICATED_FOR",
            r"HAS_KNOWN_REACTION",
        ]
        for pattern in forbidden_patterns:
            self.assertIsNone(re.search(pattern, self.cypher), msg=f"init.cypher still has generated seed snippet pattern: {pattern}")
