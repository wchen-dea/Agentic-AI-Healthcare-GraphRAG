CREATE CONSTRAINT patient_id IF NOT EXISTS
FOR (p:Patient) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT encounter_id IF NOT EXISTS
FOR (e:Encounter) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT event_id IF NOT EXISTS
FOR (e:ClinicalEvent) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT observation_id IF NOT EXISTS
FOR (o:Observation) REQUIRE o.id IS UNIQUE;

CREATE CONSTRAINT med_order_id IF NOT EXISTS
FOR (m:MedicationOrder) REQUIRE m.id IS UNIQUE;

CREATE CONSTRAINT device_reading_id IF NOT EXISTS
FOR (d:DeviceReading) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT claim_id IF NOT EXISTS
FOR (c:Claim) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT medication_name IF NOT EXISTS
FOR (m:Medication) REQUIRE m.name IS UNIQUE;

CREATE CONSTRAINT condition_name IF NOT EXISTS
FOR (c:Condition) REQUIRE c.name IS UNIQUE;

CREATE CONSTRAINT symptom_name IF NOT EXISTS
FOR (s:Symptom) REQUIRE s.name IS UNIQUE;

CREATE CONSTRAINT source_name IF NOT EXISTS
FOR (s:SourceSystem) REQUIRE s.name IS UNIQUE;

MERGE (w:Medication {name: "Warfarin"})
MERGE (a:Medication {name: "Azithromycin"})
MERGE (w)-[:INTERACTS_WITH {risk: "bleeding_risk", severity: "high"}]->(a);

MERGE (hyperkalemia:Condition {name: "Hyperkalemia"});
