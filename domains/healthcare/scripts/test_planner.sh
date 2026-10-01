#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../agent-service"
uv run --package healthcare-agent-service pytest -q \
  tests/test_planner_evaluation.py \
  tests/test_planner_edge_cases.py
