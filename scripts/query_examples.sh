#!/usr/bin/env bash
set -euo pipefail

echo "Query 1: Hyperkalemia risk evidence"
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Why might this patient have hyperkalemia risk and what evidence exists?",
    "patient_id": "patient-0001"
  }' | jq .

echo "Query 2: Vitals instability and respiratory concern"
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Summarize recent device telemetry anomalies for this patient and whether they suggest respiratory deterioration.",
    "patient_id": "patient-0012"
  }' | jq .

echo "Query 3: Medication interaction and safety"
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Check current medication orders for possible interaction risks and provide supporting graph and event evidence.",
    "patient_id": "patient-0025"
  }' | jq .

echo "Query 4: Clinical vs claims consistency"
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Compare clinical events with claim status for this patient and identify any potential documentation or coverage mismatch.",
    "patient_id": "patient-0007"
  }' | jq .

echo "Query 5: Cross-patient cohort risk overview"
curl -s -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Across recent events, which patterns indicate rising cardiometabolic risk and what evidence is most frequent?"
  }' | jq .
