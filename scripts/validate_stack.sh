#!/usr/bin/env bash
set -euo pipefail

echo "Checking Kafka topics..."
docker exec healthcare-kafka kafka-topics --bootstrap-server kafka:29092 --list

echo "Checking Schema Registry subjects..."
curl -s http://localhost:8081/subjects | jq .

echo "Checking Qdrant collections..."
curl -s http://localhost:6333/collections | jq .

echo "Checking Neo4j patients..."
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 'MATCH (p:Patient) RETURN count(p) AS patients;'

echo "Checking RAG API..."
curl -s http://localhost:8000/health | jq .
