#!/bin/sh
# Idempotent Neo4j bootstrap: wait for readiness, then apply constraints and
# ontology seeds. Fails loudly (non-zero exit) so dependent services do not
# start against an unseeded graph.
set -eu

NEO4J_URI="${NEO4J_URI:-bolt://neo4j-sc:7687}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-supplychain123}"
INIT_FILE="${NEO4J_INIT_FILE:-/init.cypher}"
SEEDS_FILE="${NEO4J_GENERATED_SEEDS_FILE:-/generated_ontology_seeds.cypher}"
MAX_ATTEMPTS="${NEO4J_BOOTSTRAP_MAX_ATTEMPTS:-60}"
RETRY_SECONDS="${NEO4J_BOOTSTRAP_RETRY_SECONDS:-2}"
OUTPUT_FILE="${NEO4J_BOOTSTRAP_OUTPUT:-/tmp/bootstrap.cypher}"

cs() {
  cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" "$@"
}

log() { echo "[neo4j-sc-bootstrap] $*"; }

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

cat "$INIT_FILE" "$SEEDS_FILE" > "$OUTPUT_FILE"
log "Applying constraints from $INIT_FILE and ontology seeds from $SEEDS_FILE"
cs -f "$OUTPUT_FILE"
log "Bootstrap complete"
