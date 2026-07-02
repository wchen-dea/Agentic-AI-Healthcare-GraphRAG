# AI QA — Accuracy and Quality Validation

## Overview

This document maps the full quality validation strategy for the Healthcare GraphRAG platform
across its three evidence paths: vector retrieval (Qdrant), graph traversal (Neo4j), and
LLM answer generation (Ollama). Each path has distinct failure modes and requires a
different validation technique.

```
Question
  │
  ├─► Vector retrieval (Qdrant ANN)       ←── Precision@k / semantic hit rate
  │         │
  ├─► Graph traversal (Neo4j Cypher)      ←── Deterministic edge assertions
  │         │
  └─► LLM synthesis (Ollama)              ←── Context grounding + golden-set scoring
              │
              └─► Response / guardrails   ←── Contract tests (CI-automated)
```

---

## 1. Contract Tests (CI-Automated)

**File:** `rag-api/tests/test_contracts.py`  
**Runner:** `python rag-api/tests/test_contracts.py` (stdlib `unittest`, no pytest)  
**CI trigger:** push or PR to `dev` touching `rag-api/**` — `.github/workflows/rag-api-contracts.yml`

These tests run entirely in-process using `fastapi.testclient.TestClient`. All three
external services (Qdrant, Neo4j, Ollama) are mocked with `unittest.mock.patch`, so no
live stack is required.

### Test inventory

| Test | What is verified |
|------|-----------------|
| `test_query_redacts_vector_text_and_writes_audit_log` | Vector text is stripped from generation-role responses; audit log is written with correct `tool_name`, `outcome`, `patient_scope`, `caller_id` |
| `test_query_enforces_role_policy` | `read_only` role returns HTTP 401 for `/query`; `generation` role succeeds |
| `test_mcp_export_defaults_to_bounded_text_and_denies_raw_payload` | `export` role returns bounded (truncated) text; `include_raw_payload=True` is silently denied; `graph_access_level` is `broader` |
| `test_generation_and_export_have_different_evidence_defaults` | `graphrag_answer_generate` redacts text (`access_level: none`); `evidence_bundle_export` returns bounded text (`access_level: bounded`) |
| `test_query_accepts_explicit_generation_role_header` | `X-Caller-Role: generation` header is respected |
| `test_query_trims_response_to_configured_budget` | Response byte budget (`RAG_API_MAX_RESPONSE_BYTES`) is enforced; `guardrails.response_truncated` is set when trimmed |

### How to run locally

The contract tests must be run with **Python 3.11** (matching Docker and CI). Running with
Python 3.14+ causes a dependency conflict: `mcp==1.28.0` requires `pydantic>=2.12.0` on
3.14, and pydantic 2.12.x has no wheel for that version yet.

```bash
cd /path/to/Agentic-AI-Healthcare-GraphRAG
python3.11 -m venv .venv311
.venv311/bin/pip install -r rag-api/requirements.txt
.venv311/bin/python rag-api/tests/test_contracts.py
```

Expected output:

```
Ran 6 tests in ~1s

OK
```

### Test harness internals

**Module isolation:** `load_module()` pops `app` from `sys.modules` and calls
`importlib.import_module("app")` for each test, giving each test a fresh module with its
own settings and connections.

**Prometheus registry fix:** `app.py` registers three Prometheus metrics (`Histogram`,
`Histogram`, `Counter`) at module scope. Because `prometheus_client.REGISTRY` is a
process-wide singleton that survives module reloads, `tearDown` must explicitly unregister
all `rag_api_*` collectors after each test, otherwise the second `load_module()` call
raises `ValueError: Duplicated timeseries`.

```python
# tearDown — Prometheus cleanup (from test_contracts.py)
rag_collectors = set(
    c
    for name, c in list(prometheus_client.REGISTRY._names_to_collectors.items())
    if name.startswith("rag_api_")
)
for collector in rag_collectors:
    try:
        prometheus_client.REGISTRY.unregister(collector)
    except Exception:
        pass
```

**pydantic pin:** `requirements.txt` pins `pydantic>=2.11.7,<3.0.0` (relaxed from
`==2.11.7`) so pip can resolve `mcp==1.28.0`'s `pydantic>=2.12.0` constraint on Python
3.11 without conflict.

### Guardrail fields validated by tests

Every `/query` and MCP tool response carries a `guardrails` block. The contract tests
assert its values explicitly:

| Field | What it means | Tested value |
|-------|--------------|--------------|
| `evidence_text_redacted` | Whether vector event text was stripped | `true` for `generation` role |
| `evidence_access_level` | `none` / `bounded` | `none` for generation, `bounded` for export |
| `graph_access_level` | `standard` / `broader` | `standard` for generation, `broader` for export |
| `response_truncated` | Budget enforcement was triggered | `true` when `MAX_RESPONSE_BYTES` exceeded |
| `raw_payload_returned` | Whether raw payload was included | Always `false` |

---

## 2. Graph Logic Validation (Deterministic Assertions)

Graph relationships written by the Flink processor are **deterministic** — given a known
input event, the output edges are fully predictable. These can be verified against a live
Neo4j instance after controlled event injection.

### 2a. Lab signal rules (`MAY_INDICATE` edges)

Produce a synthetic `LAB_RESULT` event for a known patient, then assert:

```bash
# Potassium ≥ 5.5 → Hyperkalemia
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (p:Patient {id:"patient-0001"})-[:HAS_OBSERVATION]->(o:Observation)
   -[:MAY_INDICATE]->(c:Condition)
   WHERE o.name = "Potassium" AND o.value >= 5.5
   RETURN o.value, c.name'
```

| Lab | Threshold | Expected `c.name` |
|-----|-----------|-------------------|
| Potassium | ≥ 5.5 mmol/L | Hyperkalemia |
| Glucose | ≥ 180 mg/dL | Hyperglycemia |
| HbA1c | ≥ 6.5 % | Diabetes Mellitus |
| Creatinine | > 1.2 mg/dL | Chronic Kidney Disease |
| eGFR | < 60 mL/min | Chronic Kidney Disease |
| Troponin I | > 0.04 ng/mL | Acute Myocardial Infarction |
| WBC | > 11.0 10³/µL | Infection |
| INR | > 3.0 | Anticoagulation Concern |
| LDL | > 130 mg/dL | Hyperlipidemia |
| TSH | > 4.5 mIU/L | Hypothyroidism |
| TSH | < 0.5 mIU/L | Hyperthyroidism |
| Hemoglobin | < 12.0 g/dL | Anemia |
| Sodium | < 135 mmol/L | Hyponatremia |
| Sodium | > 145 mmol/L | Hypernatremia |

### 2b. Adverse event detection (`REPORTED_ADVERSE_REACTION`)

Produce a `CLINICAL_NOTE` with a symptom that is a known adverse reaction for a medication
the patient is currently ordered:

```bash
# Patient on Lisinopril documents "cough" in a clinical note
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (ae:AdverseEvent)-[:ASSOCIATED_WITH_MEDICATION]->(m:Medication {name:"Lisinopril"})
   WHERE ae.symptom_name = "cough"
   RETURN ae.symptom_name, ae.meddra_term, ae.severity'
# Expected: meddra_term="Cough", severity="moderate"
```

### 2c. Contraindication violations

```bash
# Patients currently on Metformin who have CKD in the graph
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (p:Patient)-[:HAS_CONDITION]->(c:Condition {name:"Chronic Kidney Disease"})
   <-[:CONTRAINDICATED_FOR {reason:"lactic_acidosis_risk"}]-(m:Medication {name:"Metformin"})
   WHERE EXISTS {
     MATCH (p)-[:HAS_MEDICATION_ORDER]->(:MedicationOrder)-[:ORDERS_MEDICATION]->(m)
   }
   RETURN p.id, m.name, c.name'
```

### 2d. Drug safety seed verification (startup check)

```bash
# AdverseOutcome vocabulary seeded correctly
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (ao:AdverseOutcome) RETURN ao.code, ao.description ORDER BY ao.code'
# Expected: 6 rows — CA, DE, DS, HO, LT, OT

# HAS_KNOWN_REACTION edges present
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (:Medication)-[r:HAS_KNOWN_REACTION]->(:Symptom) RETURN count(r) AS edges'
# Expected: ≥ 20

# INTERACTS_WITH edges carry mechanism annotations
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 \
  'MATCH (m1:Medication)-[r:INTERACTS_WITH]->(m2:Medication)
   WHERE r.mechanism IS NOT NULL
   RETURN m1.name, m2.name, r.mechanism LIMIT 5'
```

---

## 3. Vector Retrieval Quality (Semantic Hit Rate)

Vector retrieval uses a deterministic stable-embedding (MD5 bag-of-words) rather than a
neural model in this repository. Accuracy is therefore bounded by vocabulary overlap
between the query and the embedded clinical text.

### Hit-rate check against a live stack

```bash
# Run the full query suite and capture vector scores
./scripts/query_examples.sh 2>/dev/null \
  | jq -r 'select(.vector_context) | .question[:60], (.vector_context | map(.score))'
```

Expected: top hit score ≥ 0.7 for patient-scoped queries; ≥ 0.5 for cohort queries.

### Precision@k evaluation

Build a small labelled set and measure retrieval accuracy:

```python
# golden_retrieval.jsonl  — one JSON object per line
# {"question": "elevated potassium", "patient_id": "patient-0001",
#  "expected_event_types": ["LAB_RESULT"]}

import json, requests

hits, total = 0, 0
for row in open("golden_retrieval.jsonl"):
    q = json.loads(row)
    r = requests.post("http://localhost:8000/query", json={
        "question": q["question"], "patient_id": q["patient_id"]
    }).json()
    returned_types = {h["event_type"] for h in r.get("vector_context", [])}
    hits += any(t in returned_types for t in q["expected_event_types"])
    total += 1

print(f"Precision@k: {hits/total:.0%} ({hits}/{total})")
```

---

## 4. Answer Grounding Validation (LLM Output Quality)

### 4a. Context citation check (no judge model needed)

Assert that facts present in `graph_context` appear in the answer text. This proves the
LLM consumed the context rather than generating unsupported claims:

```python
import requests

result = requests.post("http://localhost:8000/query", json={
    "question": "Is this patient on Warfarin and Aspirin concurrently?",
    "patient_id": "patient-0001"
}).json()

# Graph interaction must be present
interactions = [
    i for p in result["graph_context"]
    for i in p.get("interactions", [])
    if i.get("from") == "Warfarin" and i.get("to") == "Aspirin"
]
assert interactions, "Warfarin+Aspirin interaction must appear in graph_context"

# Answer must reference the clinical risk
answer = result["answer"].lower()
assert any(kw in answer for kw in ["bleeding", "interaction", "risk", "warfarin"]), \
    f"Answer did not cite drug interaction evidence: {answer[:200]}"
```

### 4b. Golden-set scoring

Manually curate 10–20 known patient scenarios. Each entry lists facts that a correct
answer must contain given the available graph and vector context.

```python
# golden_answers.jsonl
# {"question": "...", "patient_id": "...",
#  "required_facts": ["Warfarin", "bleeding_risk", "Aspirin"]}

import json, requests

scores = []
for row in open("golden_answers.jsonl"):
    q = json.loads(row)
    r = requests.post("http://localhost:8000/query", json={
        "question": q["question"], "patient_id": q["patient_id"]
    }).json()
    answer = r["answer"].lower()
    hits = sum(1 for f in q["required_facts"] if f.lower() in answer)
    score = hits / len(q["required_facts"])
    scores.append(score)
    print(f"{score:.0%}  {q['question'][:60]}")

print(f"\nMean grounding score: {sum(scores)/len(scores):.0%}")
```

Target: ≥ 70 % mean grounding score across the golden set.

### 4c. Response style variants

The `graphrag_answer_generate` tool accepts a `response_style` parameter. Validate each
style produces structurally distinct output:

| Style | Expected answer characteristics |
|-------|----------------------------------|
| `concise` | Short, bullet-point friendly, ≤ 3 sentences |
| `clinical` | Uses medical terminology, references conditions by name |
| `audit` | Cites `trace_id`, mentions evidence sources explicitly |

---

## 5. Integration Smoke Tests (Live Stack)

**File:** `scripts/mcp_smoke_test.py`  
**Requires:** running stack (`docker compose up -d`)

```bash
# MCP handshake + tool-list validation
python3 scripts/mcp_smoke_test.py

# Dual-path evidence smoke query
curl -s -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question":"hyperkalemia risk evidence","patient_id":"patient-0001"}' \
  | jq '{
      patients,
      vector_hits: (.vector_context | length),
      graph_patients: (.graph_context | length),
      has_lab_signals: (.graph_context[0].lab_signals | length > 0),
      has_answer: (.answer | length > 0)
    }'
```

Expected output:

```json
{
  "patients": ["patient-0001"],
  "vector_hits": 5,
  "graph_patients": 1,
  "has_lab_signals": true,
  "has_answer": true
}
```

---

## 6. CI Pipeline Summary

```
git push → dev branch
  │
  ├── contract-tests job
  │     ├── python 3.11 venv
  │     ├── pip install rag-api/requirements.txt
  │     └── python rag-api/tests/test_contracts.py  ← 6 tests, ~2 s
  │
  └── container-build job
        └── docker build -f rag-api/Dockerfile      ← validates image builds
```

Neither job requires live external services. The contract tests mock all three
dependencies (Qdrant, Neo4j, Ollama) and validate response shape, guardrail metadata,
role enforcement, text redaction, and byte-budget trimming.

---

## 7. What Is Not Yet Automated

| Gap | Recommended next step |
|-----|-----------------------|
| Graph integration tests after event injection | Add `rag-api/tests/test_graph_signals.py` using `neo4j` driver against a test Neo4j container in CI |
| Vector precision@k regression | Build `golden_retrieval.jsonl` with 20 labelled queries and run in CI |
| Golden-set answer grounding | Build `golden_answers.jsonl` and run grounding score check in CI |
| Adverse event detection end-to-end | Inject known medication + symptom pair, assert `AdverseEvent` node via Cypher |
| Contraindication alert end-to-end | Inject known condition + medication order, assert contraindication in `graph_context` |
| Response style regression | Add contract test variant for `response_style: audit` verifying `trace_id` in answer |
