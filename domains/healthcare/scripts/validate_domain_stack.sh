#!/usr/bin/env bash
set -euo pipefail
# Validate healthcare domain stack health.

HC_API="${RAG_API_URL:-http://localhost:8000}"
HC_NEO4J="${NEO4J_HTTP_URL:-http://localhost:7474}"
HC_QDRANT="${QDRANT_URL:-http://localhost:6333}"

echo "Healthcare stack validation"

echo -n "Neo4j...       "
curl -sf "$HC_NEO4J" > /dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "Qdrant...      "
curl -sf "$HC_QDRANT/collections" > /dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "RAG API...     "
curl -sf "$HC_API/health" > /dev/null 2>&1 && echo "OK" || echo "NOT RUNNING (expected if RAG API not yet deployed)"

echo
echo "Ontology validation:"
python3 "$(dirname "$0")/validate_ontology.py"

echo
echo "Bootstrap validation:"
python3 "$(dirname "$0")/test_neo4j_bootstrap.py"
