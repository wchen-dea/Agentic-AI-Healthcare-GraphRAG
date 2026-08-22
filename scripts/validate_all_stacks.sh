#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Shared Infrastructure ==="

echo -n "Kafka...           "
docker exec infra-kafka kafka-topics --bootstrap-server kafka:29092 --list > /dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "Schema Registry... "
curl -sf http://localhost:8081/subjects > /dev/null 2>&1 && echo "OK" || echo "FAIL"

echo -n "LocalStack...      "
curl -sf http://localhost:4566/_localstack/health > /dev/null 2>&1 && echo "OK" || echo "NOT RUNNING"

echo
echo "=== Healthcare Domain ==="
bash "$ROOT_DIR/domains/healthcare/scripts/validate_domain_stack.sh"

echo
echo "=== Supply Chain Domain ==="
bash "$ROOT_DIR/domains/supply-chain/scripts/validate_domain_stack.sh"
