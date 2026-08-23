#!/usr/bin/env python3
"""Generate supply-chain Neo4j ontology seed Cypher from ontology YAML."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml


DATA_PLATFORM_DIR = Path(__file__).resolve().parents[3] / "platform" / "supply-chain"
CONFIG_DIR = DATA_PLATFORM_DIR / "ontology"
TARGET_FILE = DATA_PLATFORM_DIR / "neo4j" / "generated_ontology_seeds.cypher"

# Mapping from risk category name to (id-suffix, description)
RISK_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "Single Source Dependency": ("single-source", "Part has only one qualified supplier"),
    "Geopolitical Exposure": ("geopolitical", "Supplier in high-risk region"),
    "Quality Failure Rate": ("quality", "Supplier exceeds defect threshold"),
    "Lead Time Volatility": ("lead-time", "Shipment lead times exceed tolerance"),
    "Financial Instability": ("financial", "Supplier financial risk indicator"),
    "Natural Disaster Exposure": ("disaster", "Facility in disaster-prone zone"),
    "Capacity Constraint": ("capacity", "Facility at or above capacity"),
    "Logistics Bottleneck": ("logistics", "Transport route congestion or closure"),
    "Regulatory Non-Compliance": ("regulatory", "Supplier lacks required certifications"),
    "Cyber Vulnerability": ("cyber", "Supplier IT infrastructure vulnerability"),
}

# Static reference data not derivable from YAML alone
STATIC_SEEDS = """\

// Known part dependency chains (bill-of-materials)
MERGE (a:Part {id: "part-00001"}) SET a.name = "MCU-ARM-Cortex-M4", a.commodity_category = "Electronics", a.criticality = "critical";
MERGE (b:Part {id: "part-00002"}) SET b.name = "MLCC-0402-100nF", b.commodity_category = "Electronics", b.criticality = "high";
MERGE (c:Part {id: "part-00003"}) SET c.name = "Power-MOSFET-N-Ch", c.commodity_category = "Electronics", c.criticality = "high";
MERGE (d:Part {id: "part-00004"}) SET d.name = "Li-Ion-Cell-18650", d.commodity_category = "Electronics", d.criticality = "critical";
MERGE (e:Part {id: "part-00005"}) SET e.name = "Connector-USB-C", e.commodity_category = "Electronics", e.criticality = "medium";
MERGE (f:Part {id: "part-00006"}) SET f.name = "PCB-4Layer-FR4", f.commodity_category = "Electronics", f.criticality = "critical";

// BOM dependencies: PCB depends on MCU, MLCC, MOSFET
MATCH (pcb:Part {id: "part-00006"}), (mcu:Part {id: "part-00001"}) MERGE (pcb)-[:DEPENDS_ON {bom_level: 1}]->(mcu);
MATCH (pcb:Part {id: "part-00006"}), (mlcc:Part {id: "part-00002"}) MERGE (pcb)-[:DEPENDS_ON {bom_level: 1}]->(mlcc);
MATCH (pcb:Part {id: "part-00006"}), (mosfet:Part {id: "part-00003"}) MERGE (pcb)-[:DEPENDS_ON {bom_level: 1}]->(mosfet);

// Known supplier risk profiles
MERGE (s1:Supplier {id: "supplier-0001"}) SET s1.name = "ShenZhen MicroElec", s1.country = "CN", s1.geopolitical_risk = true, s1.tier = "tier_1";
MERGE (s2:Supplier {id: "supplier-0002"}) SET s2.name = "Taiwan Semi Components", s2.country = "TW", s2.geopolitical_risk = true, s2.tier = "tier_1";
MERGE (s3:Supplier {id: "supplier-0003"}) SET s3.name = "Bavaria Precision GmbH", s3.country = "DE", s3.geopolitical_risk = false, s3.tier = "tier_1";
MERGE (s4:Supplier {id: "supplier-0004"}) SET s4.name = "Michigan Auto Parts", s4.country = "US", s4.geopolitical_risk = false, s4.tier = "tier_2";

// Single-source risk edges
MATCH (s1:Supplier {id: "supplier-0001"}), (mcu:Part {id: "part-00001"}) MERGE (s1)-[:SUPPLIES {exclusive: true}]->(mcu);
MATCH (s2:Supplier {id: "supplier-0002"}), (mlcc:Part {id: "part-00002"}) MERGE (s2)-[:SUPPLIES {exclusive: true}]->(mlcc);
MATCH (s1:Supplier {id: "supplier-0001"}), (risk:RiskSignal {id: "risk-geopolitical"}) MERGE (s1)-[:HAS_RISK_SIGNAL {detected_ts: datetime()}]->(risk);
MATCH (s2:Supplier {id: "supplier-0002"}), (risk:RiskSignal {id: "risk-geopolitical"}) MERGE (s2)-[:HAS_RISK_SIGNAL {detected_ts: datetime()}]->(risk);
MATCH (mcu:Part {id: "part-00001"}), (risk:RiskSignal {id: "risk-single-source"}) MERGE (mcu)-[:HAS_RISK_SIGNAL {detected_ts: datetime()}]->(risk);

// Facility seeds
MERGE (f1:Facility {id: "facility-001"}) SET f1.name = "Shanghai Port", f1.facility_type = "port", f1.country = "CN", f1.region = "APAC-China";
MERGE (f2:Facility {id: "facility-002"}) SET f2.name = "Long Beach DC", f2.facility_type = "distribution_center", f2.country = "US", f2.region = "NA-West";
MERGE (f3:Facility {id: "facility-003"}) SET f3.name = "Frankfurt Hub", f3.facility_type = "cross_dock", f3.country = "DE", f3.region = "EU-West";
MERGE (f4:Facility {id: "facility-004"}) SET f4.name = "Detroit Assembly", f4.facility_type = "factory", f4.country = "US", f4.region = "NA-East";
"""


def load_graph_seeds() -> dict:
    path = CONFIG_DIR / "graph_seeds.yaml"
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_seed_cypher() -> str:
    seeds = load_graph_seeds()
    risk_categories = seeds.get("risk_category_seeds", [])

    lines: list[str] = []
    lines.append("// Generated supply chain ontology seeds")
    lines.append("")
    lines.append("// Risk categories")

    for category in risk_categories:
        if category in RISK_DESCRIPTIONS:
            suffix, desc = RISK_DESCRIPTIONS[category]
        else:
            suffix = re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")
            desc = category
        lines.append(
            f'MERGE (:RiskSignal {{id: "risk-{suffix}", category: "{category}", description: "{desc}"}});'
        )

    lines.append(STATIC_SEEDS)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate supply-chain ontology seed Cypher")
    parser.add_argument("--check", action="store_true", help="Check if generated file is up to date")
    args = parser.parse_args()

    generated = build_seed_cypher()

    if args.check:
        if not TARGET_FILE.exists():
            print(f"FAIL: {TARGET_FILE} does not exist")
            return 1
        current = TARGET_FILE.read_text(encoding="utf-8")
        if current != generated:
            print("Generated ontology seed Cypher is out of date.")
            print("Run: python domains/supply-chain/scripts/generate_ontology_seed_cypher.py")
            return 1
        print("Generated ontology seed Cypher is up to date.")
        return 0

    TARGET_FILE.parent.mkdir(parents=True, exist_ok=True)
    TARGET_FILE.write_text(generated, encoding="utf-8")
    print(f"Wrote {TARGET_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
