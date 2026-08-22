#!/bin/sh
set -eu
sleep "${NEO4J_BOOTSTRAP_SLEEP_SECONDS:-25}"
cat "${NEO4J_INIT_FILE:-/init.cypher}" "${NEO4J_GENERATED_SEEDS_FILE:-/generated_ontology_seeds.cypher}" > "${NEO4J_BOOTSTRAP_OUTPUT:-/tmp/bootstrap.cypher}"
cypher-shell \
  -a "${NEO4J_URI:-bolt://neo4j-sc:7687}" \
  -u "${NEO4J_USER:-neo4j}" \
  -p "${NEO4J_PASSWORD:-supplychain123}" \
  -f "${NEO4J_BOOTSTRAP_OUTPUT:-/tmp/bootstrap.cypher}" || true
