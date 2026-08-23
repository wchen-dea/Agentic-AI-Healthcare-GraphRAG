#!/usr/bin/env bash
set -euo pipefail

python3 agents/tests/test_react_controller.py
python3 agents/tests/test_planner_evaluation.py
python3 agents/tests/test_planner_edge_cases.py
