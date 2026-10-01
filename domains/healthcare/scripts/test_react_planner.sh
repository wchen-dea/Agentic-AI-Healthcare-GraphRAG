#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../rag-api"
uv run --package healthcare-rag-api pytest -q \
  tests/test_react_controller.py \
  tests/test_planner_evaluation.py \
  tests/test_planner_edge_cases.py
