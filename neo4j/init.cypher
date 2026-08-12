// ── Uniqueness constraints ────────────────────────────────────────────────────

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

CREATE CONSTRAINT provider_id IF NOT EXISTS
FOR (pr:Provider) REQUIRE pr.id IS UNIQUE;

CREATE CONSTRAINT payer_name IF NOT EXISTS
FOR (pay:Payer) REQUIRE pay.name IS UNIQUE;

CREATE CONSTRAINT device_id IF NOT EXISTS
FOR (d:Device) REQUIRE d.id IS UNIQUE;

CREATE CONSTRAINT icd10_code IF NOT EXISTS
FOR (i:ICD10Code) REQUIRE i.code IS UNIQUE;

CREATE CONSTRAINT procedure_code IF NOT EXISTS
FOR (p:Procedure) REQUIRE p.code IS UNIQUE;

// ── Drug Safety: runtime constraints only (seed data is generated) ─────────────

CREATE CONSTRAINT adverse_event_id IF NOT EXISTS
FOR (ae:AdverseEvent) REQUIRE ae.id IS UNIQUE;

CREATE CONSTRAINT adverse_outcome_code IF NOT EXISTS
FOR (ao:AdverseOutcome) REQUIRE ao.code IS UNIQUE;

// All generated ontology seeds (conditions, symptoms, outcomes, interactions,
// contraindications, known reactions, and medication metadata) are executed from
// neo4j/generated_ontology_seeds.cypher via neo4j/bootstrap.sh.
