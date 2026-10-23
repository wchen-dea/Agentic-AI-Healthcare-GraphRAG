<!-- markdownlint-disable-file -->
# RPI Plan Critique: Healthcare AI P1 - evaluation depth and output safety

## Metadata

* Task ID: HC-AI-P1
* Critique date: 2026-10-23
* Plan: .copilot-tracking/plans/2026-10-23/healthcare-ai-p1-evaluation-safety-plan.md
* Critique execution: Complete
* Critique depth: standard
* Depth provenance: default
* Critique type: initial
* Earlier critique: not applicable

## Inputs and Criterion Boundary

* Task context and caller requirements: plan P1 only (evaluation depth, output safety); P0 excluded.
* Research and evidence considered: .copilot-tracking/research/2026-10-23/healthcare-ai-improvement-priorities-research.md; domains/healthcare/agent-service/src/healthcare_agent/safety/harness.py, safety/guardrails.py, agents/nodes.py, generation/synthesis.py, evaluation/gates.py, evaluation/mlflow_eval.py; tests/unit/test_harness.py, tests/unit/test_layered_runtime.py
* Decisions, dependencies, task Goals, and task Requirements considered: D1, D2, FR-001..012, NFR-001..006, P01-P03 tasks.
* Assessment boundary: static read of the plan and cited code. No tests run; thresholds and fixture counts cannot be validated.

## Coverage Assessment

| Requirement, research, phase, or task ID | Coverage | Evidence or concern |
|------------------------------------------|----------|---------------------|
| FR-001, FR-002, FR-005, FR-006, FR-007, FR-010..012; NFR-001..004 | Covered | Each cited by a task with a binding condition |
| P01-T02 / FR-003 | Partial | Harness also blocks sensitive data (SSN, card, password); PC-001 |
| FR-001 "caveat-required" verdict | Partial | Action undefined on string-returning `synthesis` path; PC-002 |
| P02-T03, P03-T01, P03-T02 | Partial | Stub-provider results measure the pipeline, not model quality; PC-003 |
| Test ownership | Missing | Not locked in plan; PC-004 |

## Verdict

* Verdict: Revise
* Rationale: The plan is credible and well-sourced, but four planner-correctable gaps could cause regression of existing PII protection, ambiguous behavior, an overstated gate meaning, and unowned test changes.

## Findings

<!-- rpi:critique id=PC-001 -->
### PC-001 [Medium]: Consolidation could drop existing sensitive-data output checks

* Related IDs: P01-T01, P01-T02, FR-002, FR-003
* Evidence: domains/healthcare/agent-service/src/healthcare_agent/safety/harness.py (`_UNSAFE_OUTPUT_PATTERNS`: SSN, credit card, password); tests/unit/test_harness.py line 86
* Concern: T01 migrates only `classify_output` patterns, and T02 says no path keeps a private pattern list. The harness sensitive-data rules are not named in either, so they may be deleted or left duplicated.
* Impact: Regression of PII-in-output blocking, or the duplication the plan aims to remove.
* Smallest useful change: Add a requirement to T01/T02 that the shared engine includes the harness sensitive-data rules and `test_harness.py` cases still pass unchanged.
* Action owner: planning_parent
* Exact resolving evidence: T01 Requirements name sensitive-data rules; T02 lists `test_harness.py` as must-pass.
* Decision route: direct_planner_correction

<!-- rpi:critique id=PC-002 -->
### PC-002 [Medium]: "Caveat-required" verdict has no defined behavior

* Related IDs: P01-T01, P01-T02, FR-001, FR-003
* Evidence: domains/healthcare/agent-service/src/healthcare_agent/generation/synthesis.py (returns plain strings, e.g. "Output blocked: ...")
* Concern: The engine returns pass, caveat-required, or block, but the plan never says what each path does for caveat-required (append a standard caveat, block, or flag). FR-003 requires paths to "agree on verdicts", which is untestable without it.
* Impact: Implementers will diverge per path, recreating the inconsistency.
* Smallest useful change: Specify in T02 that caveat-required appends a fixed standard caveat (or blocks) identically on all three paths, and add a cross-path equivalence test.
* Action owner: planning_parent
* Exact resolving evidence: T02 Requirements state the action; a test asserts equal outcomes across the three paths.
* Decision route: direct_planner_correction

<!-- rpi:critique id=PC-003 -->
### PC-003 [Medium]: Stub-provider gate scores the pipeline, not model quality

* Related IDs: P02-T03, P03-T01, P03-T02, D2
* Evidence: Plan P02-T03 Details (stub provider, in-memory retrieval); P03-T02 (replaces static results file in CI)
* Concern: With a stub LLM, factuality and caveat scores reflect scripted answers. The plan does not state what the stub emits, so must-block and factuality gates may pass or fail trivially.
* Impact: A green gate may be read as clinical-quality assurance when it only proves guardrail and scoring logic.
* Smallest useful change: Require stub answers per fixture (safe, unsafe, ungrounded variants) so each gate has a failing case, state in docs and Executive Summary that the gate validates guardrail logic, and keep the live-LLM eval as opt-in follow-up.
* Action owner: planning_parent
* Exact resolving evidence: P02-T01 schema or P02-T03 includes `stub_answer`; P03-T03 states the limitation; a negative test shows the gate failing on an unsafe stub answer.
* Decision route: direct_planner_correction

<!-- rpi:critique id=PC-004 -->
### PC-004 [Medium]: Test ownership, removals, and additions are not locked

* Related IDs: P01-P03
* Evidence: Plan tasks mention tests only in passing; existing tests `tests/unit/test_harness.py`, `tests/unit/test_layered_runtime.py`, `tests/unit/test_adversarial_inputs.py`
* Concern: The plan does not state which test files own new behavior, which are removed (none?), maximum additions, or canonical targets.
* Impact: Unbounded or duplicated test changes and unclear acceptance evidence.
* Smallest useful change: Add a short test-ownership list (for example new `tests/unit/test_clinical_rules.py`, `tests/unit/test_factuality.py`, `tests/evals/test_expanded_eval.py`), state removals as none, and name validation commands (`make test-unit`, gate command, `make validate-docs`).
* Action owner: planning_parent
* Exact resolving evidence: Plan lists owners, removals, and validation commands.
* Decision route: direct_planner_correction

## Strengths and Residual Risk

* Scope respects the P0 exclusion and does not touch deploy workflows.
* Requirements are measurable and fully traced; baseline-before-threshold approach is sound.
* Residual risk: false-positive blocks; deterministic factuality limits (both recorded).

## Questions or Blocking Evidence Gaps

* None

## Limitations

* No tests or evals were executed; fixture feasibility and threshold values are unverified.

## Recommended Next Action

* Highest-impact finding: PC-002 (shared by PC-001)
* Action owner: planning_parent
* Smallest next action: Apply the four direct corrections to the plan.
* User response required: no
