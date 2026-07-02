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

// ── Drug interaction seed data ─────────────────────────────────────────────────

MERGE (w:Medication {name: "Warfarin"})
MERGE (az:Medication {name: "Azithromycin"})
MERGE (w)-[:INTERACTS_WITH {risk: "bleeding_risk", severity: "high"}]->(az);

MERGE (w2:Medication {name: "Warfarin"})
MERGE (asp:Medication {name: "Aspirin"})
MERGE (w2)-[:INTERACTS_WITH {risk: "bleeding_risk", severity: "high"}]->(asp);

MERGE (lis:Medication {name: "Lisinopril"})
MERGE (spi:Medication {name: "Spironolactone"})
MERGE (lis)-[:INTERACTS_WITH {risk: "hyperkalemia_risk", severity: "moderate"}]->(spi);

MERGE (alb:Medication {name: "Albuterol"})
MERGE (met:Medication {name: "Metoprolol"})
MERGE (alb)-[:INTERACTS_WITH {risk: "bronchospasm_risk", severity: "moderate"}]->(met);

MERGE (mfm:Medication {name: "Metformin"})
MERGE (van:Medication {name: "Vancomycin"})
MERGE (mfm)-[:INTERACTS_WITH {risk: "nephrotoxicity_risk", severity: "moderate"}]->(van);

MERGE (w3:Medication {name: "Warfarin"})
MERGE (flu:Medication {name: "Fluconazole"})
MERGE (w3)-[:INTERACTS_WITH {risk: "bleeding_risk", severity: "high"}]->(flu);

// ── Seed Condition nodes (aligned with lab signal rules) ──────────────────────

MERGE (:Condition {name: "Hyperkalemia"});
MERGE (:Condition {name: "Hyperglycemia"});
MERGE (:Condition {name: "Diabetes Mellitus"});
MERGE (:Condition {name: "Chronic Kidney Disease"});
MERGE (:Condition {name: "Acute Myocardial Infarction"});
MERGE (:Condition {name: "Anemia"});
MERGE (:Condition {name: "Hyperlipidemia"});
MERGE (:Condition {name: "Hypothyroidism"});
MERGE (:Condition {name: "Hyperthyroidism"});
MERGE (:Condition {name: "Hyponatremia"});
MERGE (:Condition {name: "Hypernatremia"});
MERGE (:Condition {name: "Infection"});
MERGE (:Condition {name: "Anticoagulation Concern"});
MERGE (:Condition {name: "Hypertension"});
MERGE (:Condition {name: "Heart Failure"});

// ── Drug Safety: pharmacovigilance vocabulary (FAERS-aligned) ─────────────────

CREATE CONSTRAINT adverse_event_id IF NOT EXISTS
FOR (ae:AdverseEvent) REQUIRE ae.id IS UNIQUE;

CREATE CONSTRAINT adverse_outcome_code IF NOT EXISTS
FOR (ao:AdverseOutcome) REQUIRE ao.code IS UNIQUE;

// FDA FAERS adverse outcome vocabulary
MERGE (:AdverseOutcome {code: "DE", description: "Death"});
MERGE (:AdverseOutcome {code: "LT", description: "Life-Threatening"});
MERGE (:AdverseOutcome {code: "HO", description: "Hospitalization - Initial or Prolonged"});
MERGE (:AdverseOutcome {code: "DS", description: "Disability"});
MERGE (:AdverseOutcome {code: "CA", description: "Congenital Anomaly"});
MERGE (:AdverseOutcome {code: "OT", description: "Other Serious (Important Medical Events)"});

// Known adverse reactions: (Medication)-[:HAS_KNOWN_REACTION {severity, meddra_term}]->(Symptom)
// Symptom names match the producer SYMPTOMS list so streaming signal detection can fire automatically.

MERGE (war:Medication {name: "Warfarin"})
MERGE (sp1:Symptom {name: "palpitations"}) MERGE (sc1:Symptom {name: "confusion"})
MERGE (war)-[:HAS_KNOWN_REACTION {severity: "high",   meddra_term: "Palpitation"}]->(sp1)
MERGE (war)-[:HAS_KNOWN_REACTION {severity: "high",   meddra_term: "Confusion"}]->(sc1);

MERGE (lis:Medication {name: "Lisinopril"})
MERGE (sc2:Symptom {name: "cough"}) MERGE (sd1:Symptom {name: "dizziness"})
MERGE (lis)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Cough"}]->(sc2)
MERGE (lis)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Dizziness"}]->(sd1);

MERGE (ato:Medication {name: "Atorvastatin"})
MERGE (sf1:Symptom {name: "fatigue"}) MERGE (slc:Symptom {name: "leg cramps"})
MERGE (ato)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Fatigue"}]->(sf1)
MERGE (ato)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Myalgia"}]->(slc);

MERGE (amx:Medication {name: "Amoxicillin"})
MERGE (ssw:Symptom {name: "swelling"}) MERGE (ssh:Symptom {name: "shortness of breath"})
MERGE (amx)-[:HAS_KNOWN_REACTION {severity: "high",     meddra_term: "Angioedema"}]->(ssw)
MERGE (amx)-[:HAS_KNOWN_REACTION {severity: "high",     meddra_term: "Dyspnoea"}]->(ssh);

MERGE (mfm:Medication {name: "Metformin"})
MERGE (sn1:Symptom {name: "nausea"}) MERGE (sv1:Symptom {name: "vomiting"})
MERGE (mfm)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Nausea"}]->(sn1)
MERGE (mfm)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Vomiting"}]->(sv1);

MERGE (met:Medication {name: "Metoprolol"})
MERGE (sd2:Symptom {name: "dizziness"}) MERGE (sf2:Symptom {name: "fatigue"})
MERGE (met)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Dizziness"}]->(sd2)
MERGE (met)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Fatigue"}]->(sf2);

MERGE (alb:Medication {name: "Albuterol"})
MERGE (sp2:Symptom {name: "palpitations"}) MERGE (scp:Symptom {name: "chest pain"})
MERGE (alb)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Palpitation"}]->(sp2)
MERGE (alb)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Chest Pain"}]->(scp);

MERGE (lev:Medication {name: "Levothyroxine"})
MERGE (sp3:Symptom {name: "palpitations"}) MERGE (swl:Symptom {name: "weight loss"})
MERGE (lev)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Palpitation"}]->(sp3)
MERGE (lev)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Weight loss"}]->(swl);

MERGE (mor:Medication {name: "Morphine"})
MERGE (sd3:Symptom {name: "dizziness"}) MERGE (sn2:Symptom {name: "nausea"})
MERGE (mor)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Dizziness"}]->(sd3)
MERGE (mor)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Nausea"}]->(sn2);

MERGE (ser:Medication {name: "Sertraline"})
MERGE (shd:Symptom {name: "headache"}) MERGE (sn3:Symptom {name: "nausea"})
MERGE (ser)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Headache"}]->(shd)
MERGE (ser)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Nausea"}]->(sn3);

// Contraindications: (Medication)-[:CONTRAINDICATED_FOR {reason, severity}]->(Condition)
MERGE (war2:Medication {name: "Warfarin"})
MERGE (can:Condition {name: "Anemia"})
MERGE (war2)-[:CONTRAINDICATED_FOR {reason: "increased_bleeding_risk", severity: "high"}]->(can);

MERGE (lis2:Medication {name: "Lisinopril"})
MERGE (chk:Condition {name: "Hyperkalemia"})
MERGE (lis2)-[:CONTRAINDICATED_FOR {reason: "worsens_hyperkalemia", severity: "high"}]->(chk);

MERGE (mfm2:Medication {name: "Metformin"})
MERGE (cckd:Condition {name: "Chronic Kidney Disease"})
MERGE (mfm2)-[:CONTRAINDICATED_FOR {reason: "lactic_acidosis_risk", severity: "high"}]->(cckd);

MERGE (spi:Medication {name: "Spironolactone"})
MERGE (chk2:Condition {name: "Hyperkalemia"})
MERGE (spi)-[:CONTRAINDICATED_FOR {reason: "worsens_hyperkalemia", severity: "high"}]->(chk2);

MERGE (alb2:Medication {name: "Albuterol"})
MERGE (chf:Condition {name: "Heart Failure"})
MERGE (alb2)-[:CONTRAINDICATED_FOR {reason: "tachycardia_risk", severity: "moderate"}]->(chf);

MERGE (van:Medication {name: "Vancomycin"})
MERGE (cckd2:Condition {name: "Chronic Kidney Disease"})
MERGE (van)-[:CONTRAINDICATED_FOR {reason: "nephrotoxicity", severity: "high"}]->(cckd2);

// ── Extended drug-drug interactions ───────────────────────────────────────────
// Mechanism property follows the FAERS INTERACTING_DRUG model.

MERGE (asp2:Medication {name: "Aspirin"})
MERGE (clop:Medication {name: "Clopidogrel"})
MERGE (asp2)-[:INTERACTS_WITH {risk: "bleeding_risk", severity: "high", mechanism: "dual_antiplatelet_aggregation"}]->(clop);

MERGE (ato2:Medication {name: "Atorvastatin"})
MERGE (az2:Medication {name: "Azithromycin"})
MERGE (ato2)-[:INTERACTS_WITH {risk: "myopathy_risk", severity: "moderate", mechanism: "CYP3A4_inhibition_raises_statin_levels"}]->(az2);

MERGE (los:Medication {name: "Losartan"})
MERGE (spi2:Medication {name: "Spironolactone"})
MERGE (los)-[:INTERACTS_WITH {risk: "hyperkalemia_risk", severity: "moderate", mechanism: "dual_RAAS_blockade"}]->(spi2);

MERGE (fur:Medication {name: "Furosemide"})
MERGE (van2:Medication {name: "Vancomycin"})
MERGE (fur)-[:INTERACTS_WITH {risk: "nephrotoxicity_risk", severity: "high", mechanism: "synergistic_renal_toxicity"}]->(van2);

MERGE (met2:Medication {name: "Metoprolol"})
MERGE (ins:Medication {name: "Insulin Glargine"})
MERGE (met2)-[:INTERACTS_WITH {risk: "hypoglycemia_masking", severity: "moderate", mechanism: "beta_blockade_masks_tachycardia_warning_sign"}]->(ins);

MERGE (dex:Medication {name: "Dexamethasone"})
MERGE (ins2:Medication {name: "Insulin Glargine"})
MERGE (dex)-[:INTERACTS_WITH {risk: "hyperglycemia_risk", severity: "moderate", mechanism: "glucocorticoid_induced_insulin_resistance"}]->(ins2);

MERGE (clop2:Medication {name: "Clopidogrel"})
MERGE (ome:Medication {name: "Omeprazole"})
MERGE (clop2)-[:INTERACTS_WITH {risk: "reduced_antiplatelet_efficacy", severity: "moderate", mechanism: "CYP2C19_inhibition_reduces_clopidogrel_activation"}]->(ome);

MERGE (hct:Medication {name: "Hydrochlorothiazide"})
MERGE (fur2:Medication {name: "Furosemide"})
MERGE (hct)-[:INTERACTS_WITH {risk: "electrolyte_depletion", severity: "moderate", mechanism: "additive_diuresis_hypokalemia_hyponatremia"}]->(fur2);

MERGE (mor2:Medication {name: "Morphine"})
MERGE (gab:Medication {name: "Gabapentin"})
MERGE (mor2)-[:INTERACTS_WITH {risk: "respiratory_depression", severity: "high", mechanism: "additive_CNS_depression"}]->(gab);

// ── Mechanism annotations on existing INTERACTS_WITH edges ───────────────────

MATCH (m1:Medication {name: "Warfarin"})-[r:INTERACTS_WITH]->(m2:Medication {name: "Azithromycin"})
SET r.mechanism = "CYP3A4_inhibition_increases_warfarin_exposure";

MATCH (m1:Medication {name: "Warfarin"})-[r:INTERACTS_WITH]->(m2:Medication {name: "Aspirin"})
SET r.mechanism = "additive_anticoagulation_and_antiplatelet";

MATCH (m1:Medication {name: "Lisinopril"})-[r:INTERACTS_WITH]->(m2:Medication {name: "Spironolactone"})
SET r.mechanism = "dual_potassium_sparing_ACE_inhibitor_plus_K_sparing_diuretic";

MATCH (m1:Medication {name: "Albuterol"})-[r:INTERACTS_WITH]->(m2:Medication {name: "Metoprolol"})
SET r.mechanism = "pharmacological_antagonism_beta2_agonist_vs_beta_blocker";

MATCH (m1:Medication {name: "Metformin"})-[r:INTERACTS_WITH]->(m2:Medication {name: "Vancomycin"})
SET r.mechanism = "renal_competition_reduces_metformin_clearance";

MATCH (m1:Medication {name: "Warfarin"})-[r:INTERACTS_WITH]->(m2:Medication {name: "Fluconazole"})
SET r.mechanism = "CYP2C9_inhibition_markedly_raises_warfarin_INR";

// ── Extended HAS_KNOWN_REACTION ───────────────────────────────────────────────
// 12 additional medications covering the full producer MEDICATIONS list.

MERGE (az3:Medication {name: "Azithromycin"})
MERGE (sn4:Symptom {name: "nausea"}) MERGE (sob2:Symptom {name: "shortness of breath"})
MERGE (az3)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Nausea"}]->(sn4)
MERGE (az3)-[:HAS_KNOWN_REACTION {severity: "high",     meddra_term: "QT Prolongation/Dyspnoea"}]->(sob2);

MERGE (aml:Medication {name: "Amlodipine"})
MERGE (ssw2:Symptom {name: "swelling"}) MERGE (sdz2:Symptom {name: "dizziness"})
MERGE (aml)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Peripheral Oedema"}]->(ssw2)
MERGE (aml)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Dizziness"}]->(sdz2);

MERGE (ome2:Medication {name: "Omeprazole"})
MERGE (shd2:Symptom {name: "headache"}) MERGE (sn5:Symptom {name: "nausea"})
MERGE (ome2)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Headache"}]->(shd2)
MERGE (ome2)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Nausea"}]->(sn5);

MERGE (los2:Medication {name: "Losartan"})
MERGE (sdz3:Symptom {name: "dizziness"}) MERGE (shd3:Symptom {name: "headache"})
MERGE (los2)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Dizziness"}]->(sdz3)
MERGE (los2)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Headache"}]->(shd3);

MERGE (gab2:Medication {name: "Gabapentin"})
MERGE (sdz4:Symptom {name: "dizziness"}) MERGE (scf2:Symptom {name: "confusion"})
MERGE (sbv:Symptom {name: "blurred vision"})
MERGE (gab2)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Dizziness"}]->(sdz4)
MERGE (gab2)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Confusion"}]->(scf2)
MERGE (gab2)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Vision Blurred"}]->(sbv);

MERGE (hct2:Medication {name: "Hydrochlorothiazide"})
MERGE (sdz5:Symptom {name: "dizziness"}) MERGE (slc2:Symptom {name: "leg cramps"})
MERGE (hct2)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Orthostatic Hypotension"}]->(sdz5)
MERGE (hct2)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Hypokalaemia/Muscle Cramp"}]->(slc2);

MERGE (pred:Medication {name: "Prednisone"})
MERGE (swl2:Symptom {name: "weight loss"}) MERGE (sft3:Symptom {name: "fatigue"})
MERGE (sns:Symptom {name: "night sweats"})
MERGE (pred)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Weight Decreased"}]->(swl2)
MERGE (pred)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Fatigue"}]->(sft3)
MERGE (pred)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Night Sweats"}]->(sns);

MERGE (hep:Medication {name: "Heparin"})
MERGE (sob3:Symptom {name: "shortness of breath"}) MERGE (ssw3:Symptom {name: "swelling"})
MERGE (hep)-[:HAS_KNOWN_REACTION {severity: "high",     meddra_term: "Dyspnoea"}]->(sob3)
MERGE (hep)-[:HAS_KNOWN_REACTION {severity: "high",     meddra_term: "Heparin-Induced Thrombocytopenia"}]->(ssw3);

MERGE (insg:Medication {name: "Insulin Glargine"})
MERGE (scf3:Symptom {name: "confusion"}) MERGE (sdz6:Symptom {name: "dizziness"})
MERGE (insg)-[:HAS_KNOWN_REACTION {severity: "high",     meddra_term: "Hypoglycaemia/Confusion"}]->(scf3)
MERGE (insg)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Hypoglycaemia/Dizziness"}]->(sdz6);

MERGE (fur3:Medication {name: "Furosemide"})
MERGE (sdz7:Symptom {name: "dizziness"}) MERGE (slc3:Symptom {name: "leg cramps"})
MERGE (fur3)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Hypotension/Dizziness"}]->(sdz7)
MERGE (fur3)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Hypokalaemia/Muscle Cramp"}]->(slc3);

MERGE (clop3:Medication {name: "Clopidogrel"})
MERGE (shd4:Symptom {name: "headache"}) MERGE (sdz8:Symptom {name: "dizziness"})
MERGE (clop3)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Headache"}]->(shd4)
MERGE (clop3)-[:HAS_KNOWN_REACTION {severity: "low", meddra_term: "Dizziness"}]->(sdz8);

MERGE (dex2:Medication {name: "Dexamethasone"})
MERGE (sft4:Symptom {name: "fatigue"}) MERGE (swl3:Symptom {name: "weight loss"})
MERGE (dex2)-[:HAS_KNOWN_REACTION {severity: "low",      meddra_term: "Fatigue"}]->(sft4)
MERGE (dex2)-[:HAS_KNOWN_REACTION {severity: "moderate", meddra_term: "Weight Decreased"}]->(swl3);

// ── Extended CONTRAINDICATED_FOR ──────────────────────────────────────────────

MERGE (hep2:Medication {name: "Heparin"})
MERGE (can2:Condition {name: "Anemia"})
MERGE (hep2)-[:CONTRAINDICATED_FOR {reason: "increased_bleeding_risk", severity: "high"}]->(can2);

MERGE (clop4:Medication {name: "Clopidogrel"})
MERGE (can3:Condition {name: "Anemia"})
MERGE (clop4)-[:CONTRAINDICATED_FOR {reason: "increased_bleeding_risk", severity: "high"}]->(can3);

MERGE (pred2:Medication {name: "Prednisone"})
MERGE (cdm:Condition {name: "Diabetes Mellitus"})
MERGE (pred2)-[:CONTRAINDICATED_FOR {reason: "steroid_induced_hyperglycemia", severity: "moderate"}]->(cdm);

MERGE (dex3:Medication {name: "Dexamethasone"})
MERGE (cdm2:Condition {name: "Diabetes Mellitus"})
MERGE (dex3)-[:CONTRAINDICATED_FOR {reason: "glucocorticoid_raises_blood_glucose", severity: "moderate"}]->(cdm2);

MERGE (hct3:Medication {name: "Hydrochlorothiazide"})
MERGE (chn:Condition {name: "Hyponatremia"})
MERGE (hct3)-[:CONTRAINDICATED_FOR {reason: "thiazide_worsens_hyponatremia", severity: "high"}]->(chn);

MERGE (los3:Medication {name: "Losartan"})
MERGE (chk3:Condition {name: "Hyperkalemia"})
MERGE (los3)-[:CONTRAINDICATED_FOR {reason: "ARB_raises_serum_potassium", severity: "high"}]->(chk3);

MERGE (fur4:Medication {name: "Furosemide"})
MERGE (chn2:Condition {name: "Hyponatremia"})
MERGE (fur4)-[:CONTRAINDICATED_FOR {reason: "loop_diuretic_electrolyte_depletion", severity: "moderate"}]->(chn2);

MERGE (mor3:Medication {name: "Morphine"})
MERGE (cckd3:Condition {name: "Chronic Kidney Disease"})
MERGE (mor3)-[:CONTRAINDICATED_FOR {reason: "active_metabolite_accumulation", severity: "high"}]->(cckd3);

MERGE (gab3:Medication {name: "Gabapentin"})
MERGE (cckd4:Condition {name: "Chronic Kidney Disease"})
MERGE (gab3)-[:CONTRAINDICATED_FOR {reason: "requires_renal_dose_adjustment", severity: "moderate"}]->(cckd4);

MERGE (asp3:Medication {name: "Aspirin"})
MERGE (chf2:Condition {name: "Heart Failure"})
MERGE (asp3)-[:CONTRAINDICATED_FOR {reason: "fluid_retention_worsens_heart_failure", severity: "moderate"}]->(chf2);

// ── Additional Condition seeds ────────────────────────────────────────────────

MERGE (:Condition {name: "Asthma"});
MERGE (:Condition {name: "Atrial Fibrillation"});
MERGE (:Condition {name: "Hypoglycemia"});
MERGE (:Condition {name: "COPD"});
MERGE (:Condition {name: "Pancreatitis"});

// Metoprolol / beta-blockers are contraindicated in asthma
MERGE (met3:Medication {name: "Metoprolol"})
MERGE (cas:Condition {name: "Asthma"})
MERGE (met3)-[:CONTRAINDICATED_FOR {reason: "beta_blockade_induces_bronchospasm", severity: "high"}]->(cas);

// ── activeIngredient property on Medication nodes (FAERS Drug model) ─────────

MATCH (m:Medication {name: "Warfarin"})       SET m.activeIngredient = "Warfarin sodium",            m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Metformin"})      SET m.activeIngredient = "Metformin hydrochloride",    m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Atorvastatin"})   SET m.activeIngredient = "Atorvastatin calcium",       m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Levothyroxine"})  SET m.activeIngredient = "Levothyroxine sodium",       m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Sertraline"})     SET m.activeIngredient = "Sertraline hydrochloride",   m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Metoprolol"})     SET m.activeIngredient = "Metoprolol tartrate",        m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Lisinopril"})     SET m.activeIngredient = "Lisinopril",                 m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Amlodipine"})     SET m.activeIngredient = "Amlodipine besylate",        m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Omeprazole"})     SET m.activeIngredient = "Omeprazole",                 m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Clopidogrel"})    SET m.activeIngredient = "Clopidogrel bisulfate",      m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Furosemide"})     SET m.activeIngredient = "Furosemide",                 m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Gabapentin"})     SET m.activeIngredient = "Gabapentin",                 m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Losartan"})       SET m.activeIngredient = "Losartan potassium",         m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Hydrochlorothiazide"}) SET m.activeIngredient = "Hydrochlorothiazide",   m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Spironolactone"}) SET m.activeIngredient = "Spironolactone",             m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Azithromycin"})   SET m.activeIngredient = "Azithromycin",               m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Albuterol"})      SET m.activeIngredient = "Albuterol sulfate",          m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Prednisone"})     SET m.activeIngredient = "Prednisone",                 m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Morphine"})       SET m.activeIngredient = "Morphine sulfate",           m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Heparin"})        SET m.activeIngredient = "Heparin sodium",             m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Insulin Glargine"}) SET m.activeIngredient = "Insulin glargine",         m.isValidatedTradeNameUsed = true;
MATCH (m:Medication {name: "Vancomycin"})     SET m.activeIngredient = "Vancomycin hydrochloride",   m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Dexamethasone"})  SET m.activeIngredient = "Dexamethasone",              m.isValidatedTradeNameUsed = false;
MATCH (m:Medication {name: "Amoxicillin"})    SET m.activeIngredient = "Amoxicillin trihydrate",     m.isValidatedTradeNameUsed = false;
