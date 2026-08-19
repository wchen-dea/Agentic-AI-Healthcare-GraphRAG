#!/usr/bin/env bash
set -euo pipefail

echo "=== Shared Infrastructure ==="

echo "Checking Kafka topics..."
docker exec infra-kafka kafka-topics --bootstrap-server kafka:29092 --list

echo "Checking Schema Registry subjects..."
curl -s http://localhost:8081/subjects | jq .

echo "Checking LocalStack..."
curl -s http://localhost:4566/_localstack/health | jq . 2>/dev/null || echo "LocalStack not running"

echo ""
echo "=== Healthcare Domain ==="

echo "Checking Qdrant (healthcare)..."
curl -s http://localhost:6333/collections | jq .

echo "Checking Neo4j (healthcare)..."
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 'MATCH (p:Patient) RETURN count(p) AS patients;' 2>/dev/null || echo "Neo4j not running"

echo "Checking RAG API (healthcare)..."
curl -s http://localhost:8000/health | jq . 2>/dev/null || echo "RAG API not running"

echo ""
echo "=== Supply Chain Domain ==="

echo "Checking Qdrant (supply-chain)..."
curl -s http://localhost:6335/collections | jq . 2>/dev/null || echo "Qdrant (SC) not running"

echo "Checking Neo4j (supply-chain)..."
docker exec supplychain-neo4j cypher-shell -u neo4j -p supplychain123 'MATCH (n) RETURN labels(n)[0] AS label, count(n) AS cnt ORDER BY cnt DESC LIMIT 5;' 2>/dev/null || echo "Neo4j (SC) not running"

echo "Checking RAG API (supply-chain)..."
curl -s http://localhost:8001/health | jq . 2>/dev/null || echo "RAG API (SC) not running"
