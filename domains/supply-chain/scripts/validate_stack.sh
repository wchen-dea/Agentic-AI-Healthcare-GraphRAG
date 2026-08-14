#!/usr/bin/env bash
set -euo pipefail
# Validate supply-chain domain stack health.

SC_API="${SC_RAG_API_URL:-http://localhost:8001}"
SC_NEO4J="${SC_NEO4J_HTTP_URL:-http://localhost:7475}"
SC_QDRANT="${SC_QDRANT_URL:-http://localhost:6335}"

echo "Supply-chain stack validation"

echo -n "Neo4j (SC)...  "
curl -sf "$SC_NEO4J" > /dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "Qdrant (SC)... "
curl -sf "$SC_QDRANT/collections" > /dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "RAG API (SC).. "
curl -sf "$SC_API/health" > /dev/null 2>&1 && echo "OK" || echo "NOT RUNNING (expected if RAG API not yet deployed)"

echo
echo "Ontology validation:"
python3 "$(dirname "$0")/validate_ontology.py"

echo
echo "Bootstrap validation:"
python3 "$(dirname "$0")/test_neo4j_bootstrap.py"
