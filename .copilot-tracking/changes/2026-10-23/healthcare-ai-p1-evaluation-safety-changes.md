# Changes: Healthcare AI P1 evaluation depth and output safety

## Metadata

* Plan: [healthcare-ai-p1-evaluation-safety-plan.md](../../plans/2026-10-23/healthcare-ai-p1-evaluation-safety-plan.md)
* Task ID: `HC-AI-P1`
* Declared scope: full plan (P01, P02, P03)
* P0 items are maintained in a separate repo and are out of scope.

## Execution Status

Implementation complete for the full plan. All nine tasks are checked. Healthcare `tests/unit` and `tests/evals`: 289 passed, 1 skipped. Review found RV-001, which is now fixed; RV-002 and RV-003 are routed as follow-ups.

## Execution Summary

A single deterministic clinical-rule engine now backs all three output-safety paths. Evaluation grew from 5 static rows to 64 synthetic cases run through the real LangGraph guardrails, with factuality, caveat, safety and must-block gates enforced in CI.

## Completed Work

### Shared clinical output-rule engine (`P01-T01`)

* Related: FR-001..FR-004
* Files: `domains/healthcare/agent-service/src/healthcare_agent/safety/clinical_rules.py` (new), `tests/unit/test_clinical_rules.py` (new)
* Behavior: Output text gets one of three verdicts: `pass`, `caveat_required` or `block`. Self-harm, stop-medication, dosing instructions and sensitive data (SSN, card, password) block. Clinical directives without a caveat require one. Caveat detection is phrase-based, so a bare "consult" no longer counts.
* Validation: 24 unit tests passed, including benign-phrase false-positive cases.

### Every answer path uses the shared rules (`P01-T02`)

* Files: `safety/guardrails.py`, `safety/harness.py`, `agents/nodes.py`, `generation/synthesis.py`
* Behavior: The three previously divergent rule sets are gone. The graph `output_guardrail` withholds blocked answers (`output_blocked`) and appends the caveat to directives. Grounding is advisory and recorded in the trace message.
* Validation: cross-path agreement tests passed; the pre-existing suite stayed green.

### Optional output classifier port (`P01-T03`)

* Files: `safety/clinical_rules.py`
* Behavior: A provider-neutral `OutputClassifier` protocol, off by default. It can only escalate to block. A classifier error keeps the deterministic verdict and adds the reason `classifier_error`.
* Validation: escalation, error and no-relax tests passed.

### Expanded offline fixture set (`P02-T01`)

* Files: `tests/evals/fixtures/clinical_eval_cases.json` (new), `tests/evals/test_expanded_eval.py` (new)
* Behavior: 64 synthetic cases across medication safety, contraindication, lab interpretation, coding review, patient summary, cohort triage, adversarial and must-block. Each category the plan names has at least 8 cases. Routing expectations were verified by running every case.
* Validation: schema, size and category-minimum tests passed.

### Claim-level factuality scorer (`P02-T02`)

* Files: `evaluation/factuality.py` (new), `tests/unit/test_factuality.py` (new)
* Behavior: Drug, lab and condition terms in an answer must appear in retrieved evidence. Matching is word-bounded and deterministic. A test checks the term table covers the ontology vocabularies.
* Validation: 6 tests passed.

### Shared caveat matcher and offline graph runner (`P02-T03`)

* Files: `evaluation/mlflow_eval.py`, `evaluation/offline_runner.py` (new)
* Behavior: `score_safety_caveat` delegates to `has_safety_caveat`. The runner binds a stub `AgentRuntime`, runs each case through the real graph and emits routing, evidence, answer quality, factuality and safety scores.
* Validation: baseline run scored 1.00 on every metric after two fixture corrections (a contraindication question and an off-topic phrase that did not match the real guardrail).

### Calibrated gates (`P03-T01`)

* Files: `evaluation/gates.py`, `tests/evals/test_expanded_eval.py`
* Behavior: New gates for factuality (0.9), safety caveat rate (0.9), safety score (0.95) and a hard must-block gate. Must-block cases are excluded from retrieval-quality averages. `--results-file` still works, and results without the new metrics are not penalised. New flags: `--offline`, `--min-factuality`, `--min-safety-caveat`, `--min-safety`, `--cases-file`.
* Baseline: 1.00 for every score on 64 cases; thresholds keep a margin of 0.05 to 0.10.
* Validation: negative tests fail each gate on a degraded input.

### CI runs the offline graph evaluation (`P03-T02`)

* Files: `.github/workflows/agent-service-contracts.yml`
* Behavior: The existing quality-gate step now runs `gates --offline` instead of scoring the static results file. No new step or job was added.
* Validation: the offline gate ran in about 2 s locally, well inside the 3-minute budget. The workflow was not executed in CI here.

### Documentation (`P03-T03`)

* Files: `docs/05_ai_agents.md`, `docs/06_quality_assurance.md`, `docs/10_healthcare_landscape.md`
* Behavior: Documents the shared rule engine, new gates, baseline and margin, and the limits: the offline gate validates guardrail and scoring logic rather than live model quality, and factuality is term-level.
* Validation: `make validate-docs` reported 0 issues.

### Review finding RV-001: gate failure tests run real failing cases (`P03-T01`)

* Files: `tests/evals/test_expanded_eval.py`
* Behavior: The must-block and caveat gate failure tests no longer edit result dictionaries. A benign scripted answer for a must-block case now fails the hard gate, and a caveat-free non-directive answer fails the caveat gate. Both go through `run_offline_suite` and the real graph.
* Validation: the file's 8 tests passed, and the healthcare unit and eval suites passed after the change (see the Validation Summary).

### Review finding RV-002: missing offline cases file reports a clear error

* Files: `evaluation/offline_runner.py`, `evaluation/gates.py`
* Behavior: `gates --offline` with a missing cases file now prints an error naming `--cases-file` and exits with code 2, instead of a traceback.
* Validation: ran with `--cases-file /nope.json`, which printed the message and returned 2.

### Review finding RV-003: harder offline cases (`P03-T01`)

* Files: `tests/evals/fixtures/clinical_eval_cases.json`, `docs/06_quality_assurance.md`
* Behavior: six harder cases were added (`hrd-01`..`hrd-06`): three negated or conditional near-misses that must pass, and three paraphrased unsafe directives that must be blocked. The suite is 70 cases. Routing is now 0.98 because three medication questions without a medication keyword route to `patient_summary`. Every other score is 1.00 and the gate passes.
* Validation: the offline gate passed, and `tests/unit` plus `tests/evals` gave 289 passed, 1 skipped.

## Implementation-Time Plan Updates

* The classifier port is registered with a module-level `configure_output_classifier` rather than a `HealthcareAgentSettings` flag. The output paths have no settings access, and a flag with no implementation would mean nothing.
* Grounding is advisory and appears only in the trace message. An existing test pins the `guardrails` dict to `{"input_blocked": False, "output_blocked": False}`.
* `classify_output` returns passed for caveat-required text, where it used to fail. Callers that can rewrite use `apply_output_policy`.
* Fixtures gained `category` and `stub_answer` fields (critique PC-003).

## Business Alignment

None.

## Validation Summary

| Check | Result |
| --- | --- |
| Healthcare `tests/unit` and `tests/evals` | Passed (289 passed, 1 skipped) |
| `ruff` on new and edited files | Passed; 6 other pre-existing import-order findings in untouched test files were left alone |
| `make validate-docs` | Passed |
| Offline gate `--offline` | Passed, about 2 s |
| CI workflow execution | Unavailable locally |

## Remaining Work and Follow-ups

* None in plan scope.
* Follow-up: a live-LLM evaluation of model quality, and extending the term vocabulary beyond the ontology.
* Follow-up (RV-003, remaining part): the CI step time still needs checking on the first real workflow run (NFR-006, 3 minutes).
* Follow-up: the router sends medication questions without a medication keyword ("Dosing review", "Insulin guidance", "Anticoagulant review") to `patient_summary`. Cases `hrd-02`, `hrd-05` and `hrd-06` expose this.
* Follow-up: `make test-hc` has a broken recipe line (literal `\t`); tests were run with pytest directly.
