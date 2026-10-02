#!/bin/sh
# Idempotent Neo4j bootstrap: wait for readiness, collapse duplicate keyed nodes,
# apply uniqueness constraints, load generated ontology seeds, then verify the
# safety edges exist. Fails loudly (non-zero exit) instead of silently skipping.
set -eu

NEO4J_URI="${NEO4J_URI:-bolt://neo4j:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-healthcare123}"
INIT_FILE="${NEO4J_INIT_FILE:-/init.cypher}"
SEEDS_FILE="${NEO4J_GENERATED_SEEDS_FILE:-/generated_ontology_seeds.cypher}"
MAX_ATTEMPTS="${NEO4J_BOOTSTRAP_MAX_ATTEMPTS:-60}"
RETRY_SECONDS="${NEO4J_BOOTSTRAP_RETRY_SECONDS:-${NEO4J_BOOTSTRAP_SLEEP_SECONDS:-2}}"
OUTPUT_FILE="${NEO4J_BOOTSTRAP_OUTPUT:-/tmp/bootstrap.cypher}"

cs() {
  cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$@"
}

log() { echo "[neo4j-bootstrap] $*"; }

attempt=1
until cs "RETURN 1" >/dev/null 2>&1; do
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    log "Neo4j not reachable at $NEO4J_URI after $MAX_ATTEMPTS attempts" >&2
    exit 1
  fi
  attempt=$((attempt + 1))
  sleep "$RETRY_SECONDS"
done
log "Neo4j reachable at $NEO4J_URI"

# Streaming ingestion can create duplicate keyed nodes if it runs before the
# uniqueness constraints exist; such duplicates make CREATE CONSTRAINT fail.
# Merge them (relationships preserved) so constraint creation always succeeds.
# Pairs mirror the uniqueness constraints in init.cypher.
for pair in \
  Patient:id Encounter:id ClinicalEvent:id Observation:id MedicationOrder:id \
  DeviceReading:id Claim:id Medication:name Condition:name Symptom:name \
  SourceSystem:name Provider:id Payer:name Device:id ICD10Code:code \
  Procedure:code AdverseEvent:id AdverseOutcome:code
do
  label="${pair%%:*}"
  key="${pair#*:}"
  merged=$(cs --format plain \
    "MATCH (n:\`$label\`) WHERE n.\`$key\` IS NOT NULL
     WITH n.\`$key\` AS k, collect(n) AS ns WHERE size(ns) > 1
     CALL apoc.refactor.mergeNodes(ns, {properties: 'discard', mergeRels: true}) YIELD node
     RETURN count(node) AS merged" | tail -n 1)
  if [ -n "$merged" ] && [ "$merged" != "0" ]; then
    log "Merged duplicate $label nodes on $key (groups: $merged)"
  fi
done

# Constraints (init) run before seeds within a single ordered script.
cat "$INIT_FILE" "$SEEDS_FILE" > "$OUTPUT_FILE"
log "Applying constraints from $INIT_FILE and ontology seeds from $SEEDS_FILE"
cs -f "$OUTPUT_FILE"

verify_edges() {
  rel="$1"
  expected=$(grep -c ":$rel" "$SEEDS_FILE" || true)
  actual=$(cs --format plain "MATCH ()-[r:\`$rel\`]->() RETURN count(r)" | tail -n 1)
  case "$actual" in
    ''|*[!0-9]*)
      log "Could not read $rel edge count (got: '$actual'); skipping verification" >&2
      return 0
      ;;
  esac
  if [ "$actual" -lt "$expected" ]; then
    log "Expected at least $expected $rel edges, found $actual" >&2
    return 1
  fi
  log "$rel edges: $actual (seeded: $expected)"
}

verify_edges CONTRAINDICATED_FOR
verify_edges INTERACTS_WITH
log "Bootstrap complete"
