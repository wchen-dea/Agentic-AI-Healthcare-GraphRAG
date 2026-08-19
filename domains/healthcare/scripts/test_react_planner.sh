#!/usr/bin/env bash
set -euo pipefail

python3 rag-api/tests/test_react_controller.py
python3 rag-api/tests/test_planner_evaluation.py
python3 rag-api/tests/test_planner_edge_cases.py
