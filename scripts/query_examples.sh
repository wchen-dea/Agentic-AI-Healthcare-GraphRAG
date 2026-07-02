#!/usr/bin/env bash
set -euo pipefail

# ── Helpers ────────────────────────────────────────────────────────────────────
BASE="${RAG_API_URL:-http://localhost:8000}"
NEO4J_HTTP="${NEO4J_HTTP_URL:-http://localhost:7474}"
NEO4J_AUTH="$(printf '%s:%s' "${NEO4J_USER:-neo4j}" "${NEO4J_PASSWORD:-healthcare123}" | base64)"

# POST /query and pretty-print the full response.
query() {
  local label="$1" question="$2" patient="${3:-}"
  echo
  echo "=== $label ==="
  local body
  if [[ -n "$patient" ]]; then
    body=$(printf '{"question": %s, "patient_id": %s}' \
      "$(echo "$question" | jq -Rs .)" \
      "$(echo "$patient"  | jq -Rs .)")
  else
    body=$(printf '{"question": %s}' "$(echo "$question" | jq -Rs .)")
  fi
  curl -s -X POST "$BASE/query" \
    -H "Content-Type: application/json" \
    -d "$body" | jq .
}

# POST /query and show ONLY vector hits + graph signals + answer (dual-path view).
query_dual() {
  local label="$1" question="$2" patient="${3:-}" jq_filter="${4:-.}"
  echo
  echo "=== $label ==="
  local body
  if [[ -n "$patient" ]]; then
    body=$(printf '{"question": %s, "patient_id": %s}' \
      "$(echo "$question" | jq -Rs .)" \
      "$(echo "$patient"  | jq -Rs .)")
  else
    body=$(printf '{"question": %s}' "$(echo "$question" | jq -Rs .)")
  fi
  curl -s -X POST "$BASE/query" \
    -H "Content-Type: application/json" \
    -d "$body" | jq "$jq_filter"
}

# Execute a raw Cypher statement against the Neo4j HTTP transactional API.
# Returns the rows array directly — no LLM, pure graph path.
cypher() {
  local label="$1" stmt="$2"
  echo
  echo "=== $label ==="
  curl -s -X POST "$NEO4J_HTTP/db/neo4j/tx/commit" \
    -H "Content-Type: application/json" \
    -H "Authorization: Basic $NEO4J_AUTH" \
    -d "$(printf '{"statements":[{"statement":%s}]}' "$(echo "$stmt" | jq -Rs .)")" \
  | jq '.results[0].data | map(.row)'
}

# ── Original queries ───────────────────────────────────────────────────────────

query "Query 1: Hyperkalemia risk evidence" \
  "Why might this patient have hyperkalemia risk and what evidence exists?" \
  "patient-0001"

query "Query 2: Vitals instability and respiratory concern" \
  "Summarize recent device telemetry anomalies for this patient and whether they suggest respiratory deterioration." \
  "patient-0012"

query "Query 3: Medication interaction and safety" \
  "Check current medication orders for possible interaction risks and provide supporting graph and event evidence." \
  "patient-0025"

query "Query 4: Clinical vs claims consistency" \
  "Compare clinical events with claim status for this patient and identify any potential documentation or coverage mismatch." \
  "patient-0007"

query "Query 5: Cross-patient cohort risk overview" \
  "Across recent events, which patterns indicate rising cardiometabolic risk and what evidence is most frequent?"

# ── Drug safety & adverse event queries ───────────────────────────────────────

query "Query 6: Adverse drug reaction — cough on ACE inhibitor" \
  "This patient is experiencing a cough. Could this be an adverse reaction to their current medications, and is it documented in the graph?" \
  "patient-0003"

query "Query 7: Contraindication violation — Metformin with kidney disease" \
  "Does this patient have any active medications that are contraindicated given their current diagnoses or lab-indicated conditions?" \
  "patient-0018"

query "Query 8: High-severity interaction — CNS depression risk" \
  "This patient is on multiple CNS-active agents. Identify any high-severity drug interaction risks and the mechanism behind them." \
  "patient-0042"

query "Query 9: Pharmacovigilance signal — which drugs are generating adverse events" \
  "Across all patients, which medications are most frequently associated with reported adverse reactions and what symptoms are linked?"

query "Query 10: Antiplatelet efficacy concern — Clopidogrel and PPI co-prescription" \
  "Is there evidence that this patient's antiplatelet therapy may be less effective due to a concurrent PPI prescription?" \
  "patient-0055"

# ── Lab signal & clinical decision support queries ─────────────────────────────

query "Query 11: Troponin elevation — acute cardiac event risk" \
  "Recent lab results show elevated troponin. What does the graph indicate about this patient's cardiac risk, current medications, and clinical context?" \
  "patient-0030"

query "Query 12: Glycaemic control — HbA1c and diabetes management" \
  "Summarise this patient's glycaemic trend based on lab observations, current antidiabetic medications, and any relevant contraindications." \
  "patient-0015"

query "Query 13: Electrolyte panel — hyponatremia and diuretic safety" \
  "This patient has low sodium in recent labs. Correlate with their diuretic prescriptions, any contraindication flags, and clinical notes." \
  "patient-0062"

# ── Device telemetry & vital sign queries ─────────────────────────────────────

query "Query 14: Device alert correlation — tachycardia and medication context" \
  "A tachycardia alert was triggered on this patient's monitor. What medications or conditions could explain this and what does the clinical note history show?" \
  "patient-0008"

query "Query 15: Fever and infection signal from multi-source evidence" \
  "This patient has fever documented in clinical notes and elevated WBC in labs. What does the combined vector and graph evidence suggest about infection severity?" \
  "patient-0020"

# ── Claims and financial / outcome queries ────────────────────────────────────

query "Query 16: Hospitalisation claim and adverse outcome linkage" \
  "Were any of this patient's recent hospitalisations linked to an adverse drug outcome in the graph, and what was the billed cost?" \
  "patient-0044"

query "Query 17: Claims denied — diagnosis code and coverage gap analysis" \
  "This patient has denied claims. Does the documented ICD-10 coding in the graph support the procedure codes submitted, and are there coverage gaps?" \
  "patient-0033"

# ── ICD-10 / coding & cross-system queries ────────────────────────────────────

query "Query 18: ICD-10 coding completeness — conditions without coded diagnoses" \
  "Which of this patient's graph-documented conditions are missing ICD-10 codes, and what clinical notes support them?" \
  "patient-0010"

query "Query 19: Multi-condition patient — polypharmacy and interaction network" \
  "This patient has multiple chronic conditions and more than five active medications. Summarise their interaction network, known adverse reactions, and highest-priority safety concerns." \
  "patient-0050"

query "Query 20: Risk summary across all evidence sources" \
  "Provide a comprehensive risk summary for this patient combining lab signals, device alerts, adverse drug events, active contraindications, and recent claims outcomes." \
  "patient-0001"

# ══════════════════════════════════════════════════════════════════════════════
# DUAL-PATH QUERIES
# Each query below is designed so that BOTH retrieval paths contribute
# non-overlapping evidence that the LLM must synthesise:
#
#   Vector path (Qdrant)  — ANN search over clinical text embeddings.
#     Finds: semantically similar events, free-text notes, unstructured labs.
#   Graph path  (Neo4j)   — typed-relationship traversal.
#     Finds: interaction rules, MAY_INDICATE edges, HAS_KNOWN_REACTION seeds,
#            CONTRAINDICATED_FOR edges, RESULTED_IN AdverseOutcome, CODED_AS.
#
# query_dual pipes through jq to isolate the two paths in the terminal output.
# ══════════════════════════════════════════════════════════════════════════════

# ── DualPath-1: Troponin lab signal + cardiac medication interaction ───────────
# Vector: finds LAB_RESULT events with "Troponin" text at high values.
# Graph:  (Observation)-[:MAY_INDICATE]->(Acute Myocardial Infarction),
#         (Medication)-[:INTERACTS_WITH {risk: bleeding_risk}]->(Medication)
#         for Clopidogrel+Aspirin on the same patient.
query_dual "DualPath-1: Troponin + cardiac medication chain" \
  "Troponin just crossed the cardiac threshold. What does the semantic event text show about the episode, and which graph-documented medication interactions elevate the bleeding risk if antiplatelet therapy is started?" \
  "patient-0031" \
  '{
    "vector_hits": [.vector_context[] | {event_type, score, text_redacted}],
    "graph_lab_signals": [.graph_context[].lab_signals[]? | select(.indicated_condition == "Acute Myocardial Infarction")],
    "graph_interactions": [.graph_context[].interactions[]? | select(.severity == "high")],
    "answer": .answer
  }'

# ── DualPath-2: Adverse reaction confirmation — cough semantics + reaction rule ─
# Vector: retrieves CLINICAL_NOTE events whose text contains "cough" (semantic match).
# Graph:  (Lisinopril)-[:HAS_KNOWN_REACTION {meddra_term: "Cough"}]->(Symptom)
#         (Patient)-[:REPORTED_ADVERSE_REACTION]->(AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->...
query_dual "DualPath-2: Adverse reaction — cough semantics + HAS_KNOWN_REACTION rule" \
  "Find clinical note text describing a cough and use graph relationships to determine whether it is a documented adverse reaction to any current medication, citing the MedDRA term and severity." \
  "patient-0003" \
  '{
    "vector_clinical_notes": [.vector_context[] | select(.event_type == "CLINICAL_NOTE") | {score, text_redacted}],
    "graph_adverse_events": [.graph_context[].adverse_events[]?],
    "graph_contraindications": [.graph_context[].contraindications[]?],
    "answer": .answer
  }'

# ── DualPath-3: Respiratory depression risk — pharmacy text + CNS interaction ──
# Vector: finds MEDICATION_ORDER events for CNS-depressant drugs (Morphine, Gabapentin).
# Graph:  (Morphine)-[:INTERACTS_WITH {risk: "respiratory_depression", severity: "high",
#           mechanism: "additive_CNS_depression"}]->(Gabapentin)
query_dual "DualPath-3: CNS interaction — pharmacy event text + high-severity mechanism" \
  "Identify pharmacy order events for CNS-active agents and cross-reference the graph to confirm whether any combination carries a high-severity respiratory depression interaction, including the pharmacological mechanism." \
  "patient-0042" \
  '{
    "vector_pharmacy_events": [.vector_context[] | select(.event_type == "MEDICATION_ORDER") | {score, text_redacted}],
    "graph_high_severity_interactions": [.graph_context[].interactions[]? | select(.severity == "high")],
    "answer": .answer
  }'

# ── DualPath-4: Steroid-induced hyperglycaemia — cross-source pattern ───────────
# Vector: finds MEDICATION_ORDER events for Dexamethasone/Prednisone AND
#         LAB_RESULT events with elevated Glucose in the same patient context.
# Graph:  (Dexamethasone)-[:INTERACTS_WITH {risk: "hyperglycemia_risk"}]->(Insulin Glargine),
#         (Dexamethasone)-[:CONTRAINDICATED_FOR {reason: "glucocorticoid_raises_blood_glucose"}]->(Diabetes Mellitus)
#         (Observation {name: Glucose})-[:MAY_INDICATE]->(Hyperglycemia)
query_dual "DualPath-4: Steroid + glucose — pharmacy text, lab text, and graph causal chain" \
  "Is there semantic evidence that steroid administration coincided with glucose elevation, and does the graph confirm a causal interaction chain between the corticosteroid, insulin therapy, and diagnosed diabetes?" \
  "patient-0060" \
  '{
    "vector_hits_by_type": (.vector_context | group_by(.event_type) | map({type: .[0].event_type, count: length, top_score: (map(.score) | max)})),
    "graph_lab_signals": [.graph_context[].lab_signals[]? | select(.indicated_condition | test("Hyperglycemia|Diabetes"; "i"))],
    "graph_interactions": [.graph_context[].interactions[]? | select(.risk | test("hyperglycemia|glucose"; "i"))],
    "graph_contraindications": [.graph_context[].contraindications[]? | select(.reason | test("glucose|diabetes"; "i"))],
    "answer": .answer
  }'

# ── DualPath-5: Hospitalisation outcome — claims text + RESULTED_IN edge ─────
# Vector: finds CLAIM_STATUS events with high billed_amount or "institutional" text.
# Graph:  (Claim)-[:RESULTED_IN]->(AdverseOutcome {code: "HO"}),
#         (Claim)-[:FOR_PROCEDURE]->(Procedure {description: ...}),
#         (Claim)-[:SUBMITTED_TO]->(Payer)
query_dual "DualPath-5: Hospitalisation — claim event text + graph outcome and procedure chain" \
  "Which claim events in the vector store indicate a hospitalisation, and does the graph confirm an AdverseOutcome node linked to those claims along with the procedure performed and the payer?" \
  "patient-0044" \
  '{
    "vector_claim_events": [.vector_context[] | select(.event_type == "CLAIM_STATUS") | {score, text_redacted}],
    "graph_claims_with_outcomes": [.graph_context[].claims[]? | select(.status != null)],
    "answer": .answer
  }'

# ── DualPath-6: Cross-patient cohort — unfiltered vector + multi-patient graph ─
# No patient_id: vector search retrieves events from multiple patients based on
# semantic similarity, then graph context is built for ALL returned patient IDs.
# This is the only query mode where graph traversal covers >1 patient simultaneously.
query_dual "DualPath-6: Cohort — unfiltered vector finds patients; graph enriches each" \
  "Find all patients with recent evidence of drug-induced adverse reactions from semantic event text, then summarise the graph-documented severity, MedDRA term, and any contraindication violations for each." \
  "" \
  '{
    "patients_from_vector": [.vector_context[] | .patient_id] | unique,
    "patient_count": (.patients | length),
    "graph_adverse_events_per_patient": [.graph_context[] | {patient_id, adverse_events, contraindications}],
    "answer": .answer
  }'

# ── DualPath-7: ICD-10 coding gap — clinical note text + CODED_AS graph edge ──
# Vector: finds CLINICAL_NOTE events documenting a condition.
# Graph:  checks whether (Condition)-[:CODED_AS]->(ICD10Code) exists; absence = gap.
query_dual "DualPath-7: ICD-10 gap — clinical note text presence vs graph coding completeness" \
  "For conditions mentioned in clinical note text, verify whether the graph has ICD-10 codes recorded. Identify any conditions with supporting note evidence but missing coded diagnoses." \
  "patient-0010" \
  '{
    "vector_clinical_notes": [.vector_context[] | select(.event_type == "CLINICAL_NOTE") | {score}],
    "graph_coded_conditions": [.graph_context[].icd10_codes[]?],
    "graph_all_conditions": [.graph_context[].conditions[]?],
    "coding_gap_hint": "Conditions in graph_all_conditions not appearing in graph_coded_conditions lack ICD-10 codes",
    "answer": .answer
  }'

# ══════════════════════════════════════════════════════════════════════════════
# PURE GRAPH QUERIES (Neo4j HTTP transactional API — no vector, no LLM)
# These demonstrate the deterministic, relationship-based reasoning layer.
# Endpoint: POST $NEO4J_HTTP/db/neo4j/tx/commit
# ══════════════════════════════════════════════════════════════════════════════

# ── Graph-1: Adverse event signal ranking (pharmacovigilance) ─────────────────
cypher "Graph-1: Adverse event signal ranking by medication" \
  "MATCH (ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication)
   RETURN m.name AS medication,
          count(ae) AS signal_count,
          collect(DISTINCT ae.severity)[..3] AS severities,
          collect(DISTINCT ae.meddra_term)[..5] AS meddra_terms
   ORDER BY signal_count DESC LIMIT 10"

# ── Graph-2: Contraindication violations — patient currently on contraindicated drug
cypher "Graph-2: Active contraindication violations (patient on drug, has contraindicated condition)" \
  "MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)<-[ci:CONTRAINDICATED_FOR]-(m:Medication)
   WHERE EXISTS {
     MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m)
   }
   RETURN p.id AS patient_id,
          m.name AS medication,
          c.name AS contraindicated_condition,
          ci.reason AS reason,
          ci.severity AS severity
   ORDER BY ci.severity DESC, p.id LIMIT 20"

# ── Graph-3: High-severity drug interaction exposure (patient on both drugs) ───
cypher "Graph-3: Patients with high-severity interaction — both drugs on active orders" \
  "MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m1:Medication)
   MATCH (m1)-[i:INTERACTS_WITH]->(m2:Medication)
   WHERE i.severity = 'high'
     AND EXISTS {
       MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m2)
     }
   RETURN p.id AS patient_id,
          m1.name AS drug_a, m2.name AS drug_b,
          i.risk AS risk, i.mechanism AS mechanism
   ORDER BY p.id LIMIT 20"

# ── Graph-4: Lab-to-condition signal chain (MAY_INDICATE traversal) ──────────
cypher "Graph-4: Lab signals — which lab/value pairs triggered MAY_INDICATE edges" \
  "MATCH (p:Patient)-[:HAS_OBSERVATION]->(o:Observation)-[mi:MAY_INDICATE]->(c:Condition)
   RETURN o.name AS lab, o.value AS value, o.unit AS unit,
          c.name AS indicated_condition, mi.reason AS reason,
          count(DISTINCT p) AS patient_count
   ORDER BY patient_count DESC LIMIT 15"

# ── Graph-5: Hospitalisation outcome chain (Claim → AdverseOutcome) ───────────
cypher "Graph-5: Claims that resulted in hospitalisation with procedure and payer" \
  "MATCH (p:Patient)-[:HAS_CLAIM]->(cl:Claim)-[:RESULTED_IN]->(ao:AdverseOutcome {code: 'HO'})
   OPTIONAL MATCH (cl)-[:FOR_PROCEDURE]->(proc:Procedure)
   OPTIONAL MATCH (cl)-[:SUBMITTED_TO]->(pay:Payer)
   RETURN p.id AS patient_id,
          cl.claim_type AS claim_type,
          proc.code AS cpt_code,
          proc.description AS procedure,
          pay.name AS payer,
          cl.billed_amount AS billed,
          cl.status AS status,
          ao.description AS outcome
   ORDER BY cl.billed_amount DESC LIMIT 15"

# ── Graph-6: Adverse event + concurrent interaction — multi-hop safety chain ──
cypher "Graph-6: Patients with adverse event AND a concurrent drug interaction involving the same medication" \
  "MATCH (p:Patient)-[:REPORTED_ADVERSE_REACTION]->(ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication)
   MATCH (m)-[i:INTERACTS_WITH]->(m2:Medication)
   WHERE EXISTS {
     MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m2)
   }
   RETURN p.id AS patient_id,
          ae.symptom_name AS adverse_symptom,
          ae.severity AS ae_severity,
          m.name AS suspect_drug,
          m2.name AS interacting_drug,
          i.risk AS interaction_risk,
          i.mechanism AS mechanism
   ORDER BY ae.severity, i.severity DESC LIMIT 20"

# ── Original queries ───────────────────────────────────────────────────────────

query "Query 1: Hyperkalemia risk evidence" \
  "Why might this patient have hyperkalemia risk and what evidence exists?" \
  "patient-0001"

query "Query 2: Vitals instability and respiratory concern" \
  "Summarize recent device telemetry anomalies for this patient and whether they suggest respiratory deterioration." \
  "patient-0012"

query "Query 3: Medication interaction and safety" \
  "Check current medication orders for possible interaction risks and provide supporting graph and event evidence." \
  "patient-0025"

query "Query 4: Clinical vs claims consistency" \
  "Compare clinical events with claim status for this patient and identify any potential documentation or coverage mismatch." \
  "patient-0007"

query "Query 5: Cross-patient cohort risk overview" \
  "Across recent events, which patterns indicate rising cardiometabolic risk and what evidence is most frequent?"

# ── Drug safety & adverse event queries ───────────────────────────────────────

query "Query 6: Adverse drug reaction — cough on ACE inhibitor" \
  "This patient is experiencing a cough. Could this be an adverse reaction to their current medications, and is it documented in the graph?" \
  "patient-0003"

query "Query 7: Contraindication violation — Metformin with kidney disease" \
  "Does this patient have any active medications that are contraindicated given their current diagnoses or lab-indicated conditions?" \
  "patient-0018"

query "Query 8: High-severity interaction — CNS depression risk" \
  "This patient is on multiple CNS-active agents. Identify any high-severity drug interaction risks and the mechanism behind them." \
  "patient-0042"

query "Query 9: Pharmacovigilance signal — which drugs are generating adverse events" \
  "Across all patients, which medications are most frequently associated with reported adverse reactions and what symptoms are linked?"

query "Query 10: Antiplatelet efficacy concern — Clopidogrel and PPI co-prescription" \
  "Is there evidence that this patient's antiplatelet therapy may be less effective due to a concurrent PPI prescription?" \
  "patient-0055"

# ── Lab signal & clinical decision support queries ─────────────────────────────

query "Query 11: Troponin elevation — acute cardiac event risk" \
  "Recent lab results show elevated troponin. What does the graph indicate about this patient's cardiac risk, current medications, and clinical context?" \
  "patient-0030"

query "Query 12: Glycaemic control — HbA1c and diabetes management" \
  "Summarise this patient's glycaemic trend based on lab observations, current antidiabetic medications, and any relevant contraindications." \
  "patient-0015"

query "Query 13: Electrolyte panel — hyponatremia and diuretic safety" \
  "This patient has low sodium in recent labs. Correlate with their diuretic prescriptions, any contraindication flags, and clinical notes." \
  "patient-0062"

# ── Device telemetry & vital sign queries ─────────────────────────────────────

query "Query 14: Device alert correlation — tachycardia and medication context" \
  "A tachycardia alert was triggered on this patient's monitor. What medications or conditions could explain this and what does the clinical note history show?" \
  "patient-0008"

query "Query 15: Fever and infection signal from multi-source evidence" \
  "This patient has fever documented in clinical notes and elevated WBC in labs. What does the combined vector and graph evidence suggest about infection severity?" \
  "patient-0020"

# ── Claims and financial / outcome queries ────────────────────────────────────

query "Query 16: Hospitalisation claim and adverse outcome linkage" \
  "Were any of this patient's recent hospitalisations linked to an adverse drug outcome in the graph, and what was the billed cost?" \
  "patient-0044"

query "Query 17: Claims denied — diagnosis code and coverage gap analysis" \
  "This patient has denied claims. Does the documented ICD-10 coding in the graph support the procedure codes submitted, and are there coverage gaps?" \
  "patient-0033"

# ── ICD-10 / coding & cross-system queries ────────────────────────────────────

query "Query 18: ICD-10 coding completeness — conditions without coded diagnoses" \
  "Which of this patient's graph-documented conditions are missing ICD-10 codes, and what clinical notes support them?" \
  "patient-0010"

query "Query 19: Multi-condition patient — polypharmacy and interaction network" \
  "This patient has multiple chronic conditions and more than five active medications. Summarise their interaction network, known adverse reactions, and highest-priority safety concerns." \
  "patient-0050"

query "Query 20: Risk summary across all evidence sources" \
  "Provide a comprehensive risk summary for this patient combining lab signals, device alerts, adverse drug events, active contraindications, and recent claims outcomes." \
  "patient-0001"
