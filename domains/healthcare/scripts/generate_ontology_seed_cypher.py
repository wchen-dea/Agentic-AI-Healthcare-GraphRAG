from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FLINK_APP_DIR = Path(__file__).resolve().parents[3] / "data-platform" / "healthcare" / "flink-app"
if str(FLINK_APP_DIR) not in sys.path:
    sys.path.insert(0, str(FLINK_APP_DIR))


from app.ontology_loader import load_ontology_bundle  # noqa: E402


def build_seed_cypher(bundle: dict) -> str:
    graph_seeds = bundle["graph_seeds"]
    drug_safety = bundle["rule_packs"]["drug_safety"]
    lines: list[str] = []
    lines.append("// Generated from config/ontology/graph_seeds.yaml")
    lines.append("")
    lines.append("// Adverse outcomes")
    for item in drug_safety.get("adverse_outcomes", []):
        lines.append(
            f'MERGE (:AdverseOutcome {{code: "{item["code"]}", description: "{item["description"]}"}});'
        )
    lines.append("")
    lines.append("// Condition seeds")
    for name in graph_seeds.get("condition_seeds", []):
        lines.append(f'MERGE (:Condition {{name: "{name}"}});')
    lines.append("")
    lines.append("// Symptom seeds")
    for name in graph_seeds.get("symptom_seeds", []):
        lines.append(f'MERGE (:Symptom {{name: "{name}"}});')
    lines.append("")
    lines.append("// Medication metadata")
    for item in graph_seeds.get("medication_metadata", []):
        flag = "true" if item.get("is_validated_trade_name_used") else "false"
        lines.append(
            f'MATCH (m:Medication {{name: "{item["name"]}"}}) '
            f'SET m.activeIngredient = "{item["active_ingredient"]}", '
            f'm.isValidatedTradeNameUsed = {flag};'
        )

    lines.append("")
    lines.append("// Drug interactions")
    for item in drug_safety.get("interactions", []):
        lines.append(f'MERGE (:Medication {{name: "{item["from"]}"}});')
        lines.append(f'MERGE (:Medication {{name: "{item["to"]}"}});')
        lines.append(
            'MATCH (from:Medication {name: "' + item["from"] + '"}) '\
            'MATCH (to:Medication {name: "' + item["to"] + '"}) '\
            'MERGE (from)-[:INTERACTS_WITH {risk: "' + item["risk"] + '", severity: "' + item["severity"] + '", mechanism: "' + item["mechanism"] + '"}]->(to);'
        )

    lines.append("")
    lines.append("// Contraindications")
    for item in drug_safety.get("contraindications", []):
        lines.append(f'MERGE (:Medication {{name: "{item["medication"]}"}});')
        lines.append(f'MERGE (:Condition {{name: "{item["condition"]}"}});')
        lines.append(
            'MATCH (m:Medication {name: "' + item["medication"] + '"}) '\
            'MATCH (c:Condition {name: "' + item["condition"] + '"}) '\
            'MERGE (m)-[:CONTRAINDICATED_FOR {reason: "' + item["reason"] + '", severity: "' + item["severity"] + '"}]->(c);'
        )

    lines.append("")
    lines.append("// Known adverse reactions")
    for item in drug_safety.get("known_reactions", []):
        lines.append(f'MERGE (:Medication {{name: "{item["medication"]}"}});')
        lines.append(f'MERGE (:Symptom {{name: "{item["symptom"]}"}});')
        lines.append(
            'MATCH (m:Medication {name: "' + item["medication"] + '"}) '\
            'MATCH (s:Symptom {name: "' + item["symptom"] + '"}) '\
            'MERGE (m)-[:HAS_KNOWN_REACTION {severity: "' + item["severity"] + '", meddra_term: "' + item["meddra_term"] + '"}]->(s);'
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    bundle = load_ontology_bundle()
    target = REPO_ROOT / "neo4j" / "generated_ontology_seeds.cypher"
    target.write_text(build_seed_cypher(bundle), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())