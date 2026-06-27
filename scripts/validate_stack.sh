#!/usr/bin/env bash
set -euo pipefail

echo "Checking Kafka topics..."
docker exec healthcare-kafka kafka-topics --bootstrap-server kafka:29092 --list

echo "Checking Kafka cluster brokers..."
docker exec healthcare-kafka kafka-broker-api-versions --bootstrap-server kafka:29092 | grep -E 'healthcare-kafka|healthcare-kafka-2|healthcare-kafka-3|kafka:29092|kafka2:29093|kafka3:29094' || true

echo "Checking Schema Registry subjects..."
curl -s http://localhost:8081/subjects | jq .

echo "Checking Qdrant collections..."
curl -s http://localhost:6333/collections | jq .

echo "Checking Neo4j patients..."
docker exec healthcare-neo4j cypher-shell -u neo4j -p healthcare123 'MATCH (p:Patient) RETURN count(p) AS patients;'

echo "Checking RAG API..."
curl -s http://localhost:8000/health | jq .

echo "Checking LocalStack..."
curl -s http://localhost:4566/_localstack/health | jq .
