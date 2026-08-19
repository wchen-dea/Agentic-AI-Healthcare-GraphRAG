#!/usr/bin/env bash
set -euo pipefail

# Supply-chain domain query examples.
# Usage: ./domains/supply-chain/scripts/query_examples.sh

BASE="${SC_RAG_API_URL:-http://localhost:8001}"
NEO4J_HTTP="${SC_NEO4J_HTTP_URL:-http://localhost:7475}"
NEO4J_AUTH="$(printf '%s:%s' "${SC_NEO4J_USER:-neo4j}" "${SC_NEO4J_PASSWORD:-supplychain123}" | base64)"

query() {
  local label="$1" question="$2" entity="${3:-}"
  echo
  echo "=== $label ==="
  local body
  if [[ -n "$entity" ]]; then
    body=$(printf '{"question": %s, "entity_id": %s}' \
      "$(echo "$question" | jq -Rs .)" \
      "$(echo "$entity"  | jq -Rs .)")
  else
    body=$(printf '{"question": %s}' "$(echo "$question" | jq -Rs .)")
  fi
  curl -s -X POST "$BASE/query" \
    -H "Content-Type: application/json" \
    -d "$body" | jq .
}

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

# ── Supplier risk queries ─────────────────────────────────────────────────────

query "Query 1: Single-source critical parts" \
  "Which parts have only one qualified supplier and what is the geopolitical risk of that supplier?" \
  "part-00001"

query "Query 2: Supplier geopolitical exposure" \
  "List all suppliers in high-risk regions and their supplied parts." \

query "Query 3: Supplier quality scorecard" \
  "What is the defect rate trend for this supplier across recent quality inspections?" \
  "supplier-0001"

# ── Shipment and logistics queries ────────────────────────────────────────────

query "Query 4: Delayed shipments" \
  "Which shipments exceeded their expected lead time by more than 50% and what parts were affected?"

query "Query 5: Customs hold impact" \
  "Are there any shipments currently in customs hold? What parts and facilities are affected?" \
  "facility-002"

query "Query 6: Transport mode analysis" \
  "Compare ocean vs air shipment lead times for this supplier's deliveries." \
  "supplier-0002"

# ── Quality queries ───────────────────────────────────────────────────────────

query "Query 7: Quality failure trend" \
  "Which parts have the highest defect rates across all inspections?"

query "Query 8: Corrective action required" \
  "List all recent quality inspections that require corrective action and the associated suppliers."

# ── Disruption queries ────────────────────────────────────────────────────────

query "Query 9: Active disruptions" \
  "What disruptions are currently active and which parts and facilities are affected?"

query "Query 10: Disruption cascade — BOM impact" \
  "If this facility shuts down, which parts depend on affected components through the bill of materials?" \
  "facility-001"

# ── Inventory queries ─────────────────────────────────────────────────────────

query "Query 11: Below reorder point" \
  "Which parts are below their reorder point at any facility?"

query "Query 12: Days of supply risk" \
  "Which facility-part combinations have fewer than 5 days of supply remaining?" \
  "facility-004"

# ── Cross-domain queries ─────────────────────────────────────────────────────

query "Query 13: Full part risk profile" \
  "Give a complete risk profile for this part: supplier concentration, quality history, disruption exposure, and current inventory status." \
  "part-00006"

query "Query 14: Facility operational status" \
  "Summarize the operational status, capacity utilization, and active disruptions for all facilities."

# ── Pure graph queries ────────────────────────────────────────────────────────

cypher "Graph-1: BOM dependency tree" \
  "MATCH (p:Part)-[d:DEPENDS_ON*1..3]->(dep:Part)
   RETURN p.id AS assembly, p.name AS assembly_name,
          [r IN d | endNode(r).name] AS dependency_chain
   LIMIT 10"

cypher "Graph-2: Single-source parts" \
  "MATCH (s:Supplier)-[sup:SUPPLIES {exclusive: true}]->(p:Part)
   RETURN p.id AS part_id, p.name AS part_name, p.criticality AS criticality,
          s.id AS sole_supplier, s.country AS country, s.geopolitical_risk AS geo_risk
   ORDER BY p.criticality DESC"

cypher "Graph-3: Supplier risk signals" \
  "MATCH (s:Supplier)-[:HAS_RISK_SIGNAL]->(r:RiskSignal)
   RETURN s.id AS supplier, s.name AS name, s.country AS country,
          collect(r.category) AS risk_categories
   ORDER BY size(collect(r.category)) DESC LIMIT 10"

cypher "Graph-4: Facility disruption history" \
  "MATCH (f:Facility)-[:DISRUPTED_BY]->(d:DisruptionEvent)
   RETURN f.id AS facility, f.name AS name,
          d.disruption_type AS type, d.severity AS severity,
          d.estimated_duration_days AS duration_days
   ORDER BY d.severity DESC LIMIT 15"

cypher "Graph-5: Quality inspection results by supplier" \
  "MATCH (qi:QualityInspection)-[:SUPPLIED_BY]->(s:Supplier)
   RETURN s.id AS supplier, s.name AS name,
          count(qi) AS inspections,
          avg(qi.defect_rate) AS avg_defect_rate,
          sum(CASE WHEN qi.result = 'fail' THEN 1 ELSE 0 END) AS failures
   ORDER BY avg_defect_rate DESC LIMIT 10"

cypher "Graph-6: Inventory alerts — below reorder" \
  "MATCH (f:Facility)-[inv:HOLDS_INVENTORY]->(p:Part)
   WHERE inv.below_reorder = true
   RETURN f.id AS facility, p.id AS part, p.name AS part_name,
          inv.on_hand_qty AS on_hand, inv.reorder_point AS reorder_point,
          inv.days_of_supply AS days_of_supply
   ORDER BY inv.days_of_supply ASC LIMIT 15"
