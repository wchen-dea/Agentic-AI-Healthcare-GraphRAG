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

# ═══════════════════════════════════════════════════════════════════════════════
# LIFECYCLE, TEMPORAL, AND EXPANDED EVENT-FAMILY QUERIES
# These target the expanded producer source data: ADT events, allergy/intolerance,
# problem-list updates, medication administration/lifecycle, claim lifecycle chains,
# prior-auth decisions, procedure-performed events, temporal noise (late arrivals,
# corrections), and correlated follow-ups.
# ═══════════════════════════════════════════════════════════════════════════════

# ── ADT lifecycle queries ─────────────────────────────────────────────────────

query "Query 21: ADT admit-to-discharge pathway" \
  "Trace this patient's encounter lifecycle from admission through transfer to discharge. What location changes occurred and what diagnoses were documented at each phase?" \
  "patient-0005"

query "Query 22: ICU transfer with medication escalation" \
  "Was this patient transferred to ICU, and if so, did medication orders change around the transfer event? Correlate ADT location changes with pharmacy order timing." \
  "patient-0017"

query "Query 23: Discharge readiness — open problems at discharge" \
  "At the most recent discharge event, which problem-list items remained unresolved and are there outstanding lab abnormalities?" \
  "patient-0023"

# ── Allergy and intolerance queries ───────────────────────────────────────────

query "Query 24: Allergy intolerance — Penicillin cross-reactivity" \
  "This patient has a documented Penicillin allergy. Are any current antibiotic orders in a cross-reactive drug class, and what reaction severity is recorded?" \
  "patient-0009"

query "Query 25: Adverse reaction vs allergy distinction" \
  "Distinguish between documented adverse drug reactions and allergy/intolerance records for this patient. Which substances overlap and what was the most severe reaction?" \
  "patient-0035"

# ── Problem-list update queries ───────────────────────────────────────────────

query "Query 26: Problem-list add vs resolve trend" \
  "How many conditions were added versus resolved on this patient's problem list recently? Are any resolved conditions still generating active lab signals?" \
  "patient-0041"

query "Query 27: Problem-list coding consistency" \
  "For each problem-list entry, verify that a corresponding ICD-10 code exists in the graph. Flag any conditions added without coded diagnoses." \
  "patient-0014"

# ── Medication administration and lifecycle queries ───────────────────────────

query "Query 28: Medication lifecycle — ordered to administered" \
  "Track this patient's most recent medication order through its lifecycle: ordered, verified, administered. Were any orders held or discontinued before administration?" \
  "patient-0022"

query "Query 29: Held medication — safety signal" \
  "Which medications for this patient were placed on hold status? Does the graph show a concurrent lab abnormality or contraindication that may have triggered the hold?" \
  "patient-0048"

query "Query 30: Medication administration site and timing" \
  "Summarise inpatient vs outpatient medication administration events for this patient. Are any high-alert medications being administered outside a monitored setting?" \
  "patient-0061"

# ── Claim lifecycle chain queries ─────────────────────────────────────────────

query "Query 31: Claim lifecycle progression — submitted to paid" \
  "Follow this patient's claim lifecycle from submission through adjudication. At which stage did the claim stall, and what procedure and diagnosis codes are involved?" \
  "patient-0028"

query "Query 32: Denied then appealed claims — success rate" \
  "For this patient, how many claims were denied and subsequently appealed? Of those appealed, which reached approved or paid status?" \
  "patient-0036"

query "Query 33: Claim lifecycle vs clinical timeline alignment" \
  "Compare the timing of claim lifecycle status changes with ADT events and medication orders. Are there claim submissions that lack supporting clinical documentation?" \
  "patient-0019"

# ── Prior-authorization decision queries ──────────────────────────────────────

query "Query 34: Prior-auth denial — imaging procedure" \
  "Was prior authorization denied for any imaging procedure on this patient? What CPT code was submitted and what was the payer's decision?" \
  "patient-0057"

query "Query 35: Prior-auth decision turnaround" \
  "Across this patient's prior-auth requests, how quickly did decisions move from pending to approved or denied? Are any still pending?" \
  "patient-0073"

# ── Procedure-performed queries ───────────────────────────────────────────────

query "Query 36: Procedure performed — post-procedure lab monitoring" \
  "After this patient's most recent procedure, were follow-up labs ordered and did any values become abnormal? Connect procedure codes to subsequent lab events." \
  "patient-0045"

query "Query 37: Procedure cost vs allowed amount variance" \
  "For procedures performed on this patient, what is the variance between billed and allowed amounts? Flag any procedures where the allowed amount is less than 50% of billed." \
  "patient-0082"

# ── Temporal noise and correction queries ─────────────────────────────────────

query "Query 38: Late-arriving events — clinical impact" \
  "Identify any late-arriving events for this patient where the event timestamp predates the ingestion window by more than an hour. Could delayed lab results have affected treatment decisions?" \
  "patient-0011"

query "Query 39: Correction events — amended records" \
  "Are there correction events in this patient's record that amend prior clinical notes or lab results? What was the original event and what changed?" \
  "patient-0032"

# ── Correlated follow-up queries ─────────────────────────────────────────────

query "Query 40: Critical lab to medication response chain" \
  "When this patient's potassium or troponin crossed a critical threshold, was a correlated medication administration event generated? Trace the lab-to-intervention chain." \
  "patient-0004"

query "Query 41: Abnormal lactate with correlated intervention" \
  "This patient had elevated lactate. Was a follow-up medication administration correlated with that lab event? What drug was administered and by whom?" \
  "patient-0026"

# ── Expanded entity pool and skew queries ─────────────────────────────────────

query "Query 42: Hot-patient event density" \
  "This patient appears in the hot-entity pool. Summarise the volume and diversity of events generated — how many distinct event types, providers, and encounter locations appear?" \
  "patient-0001"

query "Query 43: Long-tail patient coverage" \
  "Does this patient from the long-tail pool have sufficient event coverage for a meaningful risk assessment, or are there evidence gaps?" \
  "patient-0850"

# ── Cross-family lifecycle queries ────────────────────────────────────────────

query "Query 44: Full encounter lifecycle — ADT to claim to payment" \
  "Trace this patient's complete encounter lifecycle: admission, clinical notes, lab orders, medication administration, discharge, procedure claim submission, and payment status." \
  "patient-0015"

query "Query 45: Medication lifecycle with concurrent claim denial" \
  "For this patient, did any medication that progressed through the full lifecycle (ordered to administered) have a concurrent claim denied? What was the denial reason?" \
  "patient-0039"

# ── Shift-handoff burst queries ───────────────────────────────────────────────

query "Query 46: Shift-handoff event clustering" \
  "Are there clusters of events for this patient that coincide with typical shift-handoff windows (0700, 1500, 2300 UTC)? Do handoff periods show higher rates of medication orders or ADT transfers?" \
  "patient-0008"

# ══════════════════════════════════════════════════════════════════════════════
# MULTI-AGENT USE CASE — Polypharmacy Medication Safety Review
#
# This scenario is the primary multi-agent demonstration case. It exercises
# all three specialist agents (medication safety, lab interpretation, coding
# review) and the confidence-gated re-retrieval loop in LangGraph mode.
#
# Scenario: A polypharmacy patient on anticoagulant + antiplatelet + dual
# potassium-sparing agents with CKD and abnormal labs. The multi-agent
# graph routes through triage → retrieval → medication_safety_agent, which
# extracts interaction chains, contraindication violations confirmed by lab
# signals, and adverse event patterns that a single-pass pipeline would
# only pass as raw context to the LLM without structured risk extraction.
# ══════════════════════════════════════════════════════════════════════════════

query "MultiAgent-1: Polypharmacy interaction cascade — anticoagulant + antiplatelet" \
  "Review medication safety: this patient is on both anticoagulant and antiplatelet agents. Are there dangerous drug-drug interactions, and what is the combined bleeding risk based on graph evidence and clinical events?" \
  "patient-0001"

query "MultiAgent-2: Contraindication chain — potassium-sparing drugs with hyperkalemia" \
  "This patient has elevated potassium. Are any current medications contraindicated for hyperkalemia? Trace the causal chain from lab result to condition to contraindication rule." \
  "patient-0001"

query "MultiAgent-3: Dual RAAS blockade — ACE inhibitor + potassium-sparing diuretic" \
  "Is this patient on both an ACE inhibitor and a potassium-sparing diuretic? What is the interaction risk, severity, and mechanism? Cross-reference with lab signals for potassium." \
  "patient-0001"

query "MultiAgent-4: Multi-condition risk surface — CKD + diabetes + polypharmacy" \
  "This patient has multiple chronic conditions and several active medications. Provide a comprehensive safety assessment: interactions, contraindications, lab-confirmed risks, and adverse reaction history." \
  "patient-0050"

query "MultiAgent-5: Adverse reaction correlation — symptom in notes vs known reaction" \
  "The patient's clinical notes mention dizziness and nausea. Cross-reference these symptoms against known adverse reactions for all active medications and determine which drug is the most likely cause." \
  "patient-0003"

query "MultiAgent-6: Steroid-insulin conflict with lab confirmation" \
  "This patient is on both a corticosteroid and insulin. Does the graph show a hyperglycemia interaction risk? Confirm with lab glucose or HbA1c signals." \
  "patient-0015"

query_dual "DualPath-MultiAgent-1: Full polypharmacy safety review — vector events + graph safety network" \
  "For a patient on Warfarin, Aspirin, Lisinopril, and Spironolactone: find medication order events in vector context, then cross-reference the graph for all drug interactions, contraindications against active conditions, lab signals that confirm risk conditions, and any documented adverse reactions." \
  "patient-0001" \
  '{
    "vector_medication_events": [.vector_context[] | select(.event_type == "MEDICATION_ORDER") | {score, text_redacted}],
    "vector_lab_events": [.vector_context[] | select(.event_type == "LAB_RESULT") | {score, text_redacted}],
    "graph_interactions": [.graph_context[].interactions[]?],
    "graph_contraindications": [.graph_context[].contraindications[]?],
    "graph_lab_signals": [.graph_context[].lab_signals[]?],
    "graph_adverse_events": [.graph_context[].adverse_events[]?],
    "graph_medications": [.graph_context[].medications[]? | {medication, dose, order_type}],
    "answer": .answer
  }'

query_dual "DualPath-MultiAgent-2: CNS depression multi-drug chain — opioid + gabapentinoid + SSRI" \
  "Identify all CNS-active medications for this patient from vector pharmacy events, then use the graph to map the full interaction network: respiratory depression risk, serotonin syndrome risk, and mechanism annotations." \
  "patient-0042" \
  '{
    "vector_pharmacy_events": [.vector_context[] | select(.event_type == "MEDICATION_ORDER") | {score, text_redacted}],
    "graph_interactions": [.graph_context[].interactions[]? | select(.severity == "high")],
    "graph_adverse_events": [.graph_context[].adverse_events[]?],
    "graph_conditions": [.graph_context[].conditions[]?],
    "answer": .answer
  }'

cypher "Graph-MultiAgent-1: Active high-severity interaction pairs — both drugs currently ordered" \
  "MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(mo1:MedicationOrder)-[:ORDERS_MEDICATION]->(m1:Medication)
         -[i:INTERACTS_WITH]->(m2:Medication)<-[:ORDERS_MEDICATION]-(mo2:MedicationOrder)<-[:HAS_MEDICATION_ORDER]-(p)
   WHERE i.severity = 'high'
     AND NOT mo1.order_type IN ['discontinued', 'hold']
     AND NOT mo2.order_type IN ['discontinued', 'hold']
   RETURN p.id AS patient_id,
          m1.name AS drug_a, m2.name AS drug_b,
          i.risk AS risk, i.mechanism AS mechanism
   ORDER BY p.id LIMIT 20"

cypher "Graph-MultiAgent-2: Contraindications confirmed by lab signals" \
  "MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition)<-[:CONTRAINDICATED_FOR]-(m:Medication)
   WHERE EXISTS {
     MATCH (p)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m)
     WHERE NOT mo.order_type IN ['discontinued', 'hold']
   }
   WITH p, m, c
   OPTIONAL MATCH (p)-[:HAS_OBSERVATION]->(o:Observation)-[:MAY_INDICATE]->(c)
   RETURN p.id AS patient_id,
          m.name AS medication,
          c.name AS contraindicated_condition,
          collect(DISTINCT {lab: o.name, value: o.value, unit: o.unit})[..3] AS confirming_labs
   ORDER BY p.id LIMIT 15"

cypher "Graph-MultiAgent-3: Patients with triple risk — interaction + contraindication + adverse event" \
  "MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
   WHERE NOT mo.order_type IN ['discontinued', 'hold']
   WITH p, collect(DISTINCT m) AS active_meds
   WHERE size(active_meds) >= 3
   OPTIONAL MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m1:Medication)
                  -[i:INTERACTS_WITH {severity: 'high'}]->(m2:Medication)
                  <-[:ORDERS_MEDICATION]-(:MedicationOrder)<-[:HAS_MEDICATION_ORDER]-(p)
   WITH p, active_meds, collect(DISTINCT {from: m1.name, to: m2.name, risk: i.risk})[..5] AS interactions
   WHERE size(interactions) > 0
   OPTIONAL MATCH (p)-[:HAS_CONDITION]->(c:Condition)<-[ci:CONTRAINDICATED_FOR]-(cm:Medication)
   WHERE cm IN active_meds
   WITH p, interactions, collect(DISTINCT {med: cm.name, condition: c.name})[..5] AS contras
   OPTIONAL MATCH (p)-[:REPORTED_ADVERSE_REACTION]->(ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(am:Medication)
   WHERE am IN active_meds
   RETURN p.id AS patient_id,
          size(interactions) AS interaction_count,
          interactions[..3] AS top_interactions,
          size(contras) AS contraindication_count,
          contras[..3] AS top_contraindications,
          collect(DISTINCT {symptom: ae.symptom_name, med: am.name, severity: ae.severity})[..3] AS adverse_events
   ORDER BY interaction_count DESC, contraindication_count DESC LIMIT 10"

# ══════════════════════════════════════════════════════════════════════════════
# EXPANDED DUAL-PATH QUERIES — lifecycle and temporal noise
# ══════════════════════════════════════════════════════════════════════════════

query_dual "DualPath-8: ADT lifecycle + medication administration chain" \
  "Did this patient's transfer to ICU coincide with escalation to IV medication administration? Show the vector evidence for ADT and pharmacy events alongside graph medication order and encounter relationships." \
  "patient-0017" \
  '{
    "vector_adt_events": [.vector_context[] | select(.event_type == "CLINICAL_NOTE") | {score, text_redacted}],
    "vector_pharmacy_events": [.vector_context[] | select(.event_type == "MEDICATION_ORDER") | {score, text_redacted}],
    "graph_medications": [.graph_context[].medications[]?],
    "graph_conditions": [.graph_context[].conditions[]?],
    "answer": .answer
  }'

query_dual "DualPath-9: Claim lifecycle denial + ICD-10 coding gap" \
  "For denied claims, does the vector store contain matching clinical notes supporting the diagnosis, and does the graph show ICD-10 codes for the claimed conditions? Identify claim denials that may stem from coding gaps." \
  "patient-0036" \
  '{
    "vector_claim_events": [.vector_context[] | select(.event_type == "CLAIM_STATUS") | {score, text_redacted}],
    "vector_clinical_notes": [.vector_context[] | select(.event_type == "CLINICAL_NOTE") | {score, text_redacted}],
    "graph_claims": [.graph_context[].claims[]?],
    "graph_icd10_codes": [.graph_context[].icd10_codes[]?],
    "answer": .answer
  }'

query_dual "DualPath-10: Allergy intolerance + medication contraindication" \
  "Are there allergy/intolerance events in the vector store for this patient, and does the graph confirm a CONTRAINDICATED_FOR relationship between the allergen substance and any active medication?" \
  "patient-0009" \
  '{
    "vector_allergy_events": [.vector_context[] | select(.event_type == "CLINICAL_NOTE") | {score, text_redacted}],
    "graph_contraindications": [.graph_context[].contraindications[]?],
    "graph_adverse_events": [.graph_context[].adverse_events[]?],
    "answer": .answer
  }'

query_dual "DualPath-11: Late-arriving lab correction + treatment chain" \
  "Did a late-arriving correction event for a lab result change the clinical picture? Show the vector text evidence for the original and corrected events, and the graph lab signals that resulted." \
  "patient-0032" \
  '{
    "vector_lab_events": [.vector_context[] | select(.event_type == "LAB_RESULT") | {score, text_redacted}],
    "graph_lab_signals": [.graph_context[].lab_signals[]?],
    "graph_medications": [.graph_context[].medications[]?],
    "answer": .answer
  }'

# ══════════════════════════════════════════════════════════════════════════════
# EXPANDED PURE GRAPH QUERIES — lifecycle, temporal, and new event families
# ══════════════════════════════════════════════════════════════════════════════

cypher "Graph-7: ADT encounter flow — admit/transfer/discharge per patient" \
  "MATCH (p:Patient)-[:PARTICIPATED_IN]->(e:Encounter)-[:HAS_EVENT]->(ce:ClinicalEvent)
   WHERE ce.source_system = 'ADTSystem'
   RETURN p.id AS patient_id,
          e.id AS encounter_id,
          collect(ce.event_type)[..5] AS event_types,
          count(ce) AS adt_event_count
   ORDER BY adt_event_count DESC LIMIT 15"

cypher "Graph-8: Medication lifecycle — orders by status" \
  "MATCH (p:Patient)-[:HAS_MEDICATION_ORDER]->(mo:MedicationOrder)-[:ORDERS_MEDICATION]->(m:Medication)
   RETURN m.name AS medication,
          mo.order_type AS lifecycle_status,
          count(DISTINCT p) AS patient_count
   ORDER BY patient_count DESC LIMIT 20"

cypher "Graph-9: Claim lifecycle distribution — status counts" \
  "MATCH (p:Patient)-[:HAS_CLAIM]->(cl:Claim)
   RETURN cl.status AS claim_status,
          count(cl) AS count,
          avg(cl.billed_amount) AS avg_billed,
          avg(cl.allowed_amount) AS avg_allowed
   ORDER BY count DESC"

cypher "Graph-10: Patients with both denied claims and active contraindications" \
  "MATCH (p:Patient)-[:HAS_CLAIM]->(cl:Claim)
   WHERE cl.status = 'denied'
   WITH p, count(cl) AS denied_count
   MATCH (p)-[:HAS_CONDITION]->(c:Condition)<-[:CONTRAINDICATED_FOR]-(m:Medication)
   WHERE EXISTS {
     MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m)
   }
   RETURN p.id AS patient_id,
          denied_count,
          collect(DISTINCT m.name)[..3] AS contraindicated_meds,
          collect(DISTINCT c.name)[..3] AS conditions
   ORDER BY denied_count DESC LIMIT 10"

cypher "Graph-11: Late-arriving events — correction chain" \
  "MATCH (ce:ClinicalEvent)
   WHERE ce.payload_json CONTAINS 'is_correction'
     AND ce.payload_json CONTAINS 'true'
   RETURN ce.event_type AS event_type,
          ce.source_system AS source_system,
          count(ce) AS correction_count
   ORDER BY correction_count DESC LIMIT 10"

cypher "Graph-12: Correlated lab-to-medication follow-ups" \
  "MATCH (ce:ClinicalEvent)
   WHERE ce.payload_json CONTAINS 'correlated_with_lab_event_id'
   RETURN ce.event_type AS event_type,
          ce.source_system AS source_system,
          count(ce) AS correlated_followup_count
   ORDER BY correlated_followup_count DESC LIMIT 10"
