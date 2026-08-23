// Generated supply chain ontology seeds

// Risk categories
MERGE (:RiskSignal {id: "risk-single-source", category: "Single Source Dependency", description: "Part has only one qualified supplier"});
MERGE (:RiskSignal {id: "risk-geopolitical", category: "Geopolitical Exposure", description: "Supplier in high-risk region"});
MERGE (:RiskSignal {id: "risk-quality", category: "Quality Failure Rate", description: "Supplier exceeds defect threshold"});
MERGE (:RiskSignal {id: "risk-lead-time", category: "Lead Time Volatility", description: "Shipment lead times exceed tolerance"});
MERGE (:RiskSignal {id: "risk-financial", category: "Financial Instability", description: "Supplier financial risk indicator"});
MERGE (:RiskSignal {id: "risk-disaster", category: "Natural Disaster Exposure", description: "Facility in disaster-prone zone"});
MERGE (:RiskSignal {id: "risk-capacity", category: "Capacity Constraint", description: "Facility at or above capacity"});
MERGE (:RiskSignal {id: "risk-logistics", category: "Logistics Bottleneck", description: "Transport route congestion or closure"});
MERGE (:RiskSignal {id: "risk-regulatory", category: "Regulatory Non-Compliance", description: "Supplier lacks required certifications"});
MERGE (:RiskSignal {id: "risk-cyber", category: "Cyber Vulnerability", description: "Supplier IT infrastructure vulnerability"});

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
