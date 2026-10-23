<!-- markdownlint-disable-file -->
# Task Research: healthcare-ai-improvement-priorities

| Field              | Value                                 |
|--------------------|---------------------------------------|
| Date               | 2026-10-23                            |
| Researcher / agent | rpi-research                          |
| Output mode        | convergence                           |

## Executive Summary

* Bottom line: The healthcare agent is a well-structured reference platform, but the largest gaps are not the roadmap features in `docs/10`. They are production-configuration and release-gate gaps: production Helm values leave human review, durable checkpointing and fail-closed auditing off, the production deploy is not gated on CI or evals, and evaluation is too thin to detect clinical-safety regressions.
* Why this matters: The repo's own roadmap prioritizes capabilities (factuality, shared checkpointer). Several of those capabilities already exist in code but are not enabled where they matter, so the cheapest, highest-risk reductions come from configuration and gating.
* Research status: Complete for static code and config analysis. No tests or services were run.
* Confidence and uncertainty: High on what the files say. Medium on runtime effect. Production may be configured outside this repo (external Secrets, gateway, branch protection); that is unverified (see D1).

## What You May Not Know

* Production patient-scope auth is enabled in Helm (`PATIENT_SCOPE_AUTH_REQUIRED: "true"`), but the application default is `false`, so any other environment started without the flag is fail-open.
* `HITL_ENABLED`, `AUDIT_FAIL_CLOSED` and `LANGGRAPH_CHECKPOINT_*` are set only in `values-dev.yaml`. Production inherits defaults: human review off, audit write failures tolerated, in-memory checkpointer fallback.
* The CI "evaluation gate" scores a 5-row static JSON fixture with a 0.5 minimum. It cannot detect a regression in live behavior.

## Findings

### 1. Production does not enable the safety controls that dev enables

Production Helm values set the role header off and patient-scope auth on, but omit human-in-the-loop review, fail-closed audit and a required Postgres checkpointer. Code defaults make each off or degraded. `get_checkpointer()` silently falls back to a process-local `InMemorySaver` when the Postgres URI is empty or setup fails, unless `LANGGRAPH_CHECKPOINT_REQUIRED` is truthy. With multiple replicas, a pending review could be lost or unreachable.

* Questions: Q2
* Evidence state: evidence-backed finding
* Evidence: C1, C2, C3, C4
* Confidence and limits: High for repo state. Production could inject these through config outside this repo.

### 2. Production deploy is not gated by tests or evaluation

CI triggers on `dev` pushes and PRs only. The deploy workflow triggers on `prd` pushes, has one job, and has no dependency on any test, eval or lint job.

* Questions: Q3
* Evidence state: evidence-backed finding
* Evidence: C5, C6
* Confidence and limits: High on workflow files. Branch protection or promotion outside the repo could compensate.

### 3. Evaluation is too small and lenient to protect clinical safety

CI gate thresholds are 0.5-0.6 on routing, evidence and answer quality, applied to 5 canned result rows, plus 12 planner fixtures and a 25-case retrieval benchmark. There is no factuality or hallucination gate, and the safety-caveat scorer is offline only. The repo roadmap already lists factuality as High.

* Questions: Q3
* Evidence state: evidence-backed finding
* Evidence: C6, C7, C8, C9
* Confidence and limits: High. A larger private eval set elsewhere is unverified.

### 4. Output safety is regex-based and easy to evade

Output guardrails match a few phrases (such as "stop taking all medications now") and flag clinical directives lacking the words "advisory" or "clinical review". Input guardrails are injection and off-topic patterns. This is a weak last line of defense for a medication-safety domain.

* Questions: Q4
* Evidence state: evidence-backed finding
* Evidence: C10
* Confidence and limits: High on code; not tested against real adversarial input.

### 5. Identity and PHI handling need hardening before real data

* Caller identity is the client-supplied `X-Caller-Id` header, trusted from a gateway; the service validates no token.
* MLflow root spans record the raw `question` and `patient_id` as inputs, with no redaction.
* The audit sink is a local JSONL file. No rate limiting was found.
* The repo is scoped to synthetic data, so this is a pre-production priority, not a current defect.

* Questions: Q4
* Evidence state: evidence-backed finding; rate-limit absence is partially supported (single grep)
* Evidence: C4, C11, C12, C13
* Confidence and limits: Medium-high.

### 6. The repo's roadmap is valid but sits behind the configuration gaps

`docs/10` lists durable memory lifecycle, factuality and shared checkpointer as High; specialist verification, self-critique, NER and neural reranking as Medium. The shared checkpointer is largely implemented (Postgres path) and needs enabling and a test, not a build. `fusion_rerank` is score fusion, not a cross-encoder, matching the doc's gap.

* Questions: Q1
* Evidence state: evidence-backed finding
* Evidence: C14, C1, C15
* Confidence and limits: High.

## Recommendation and Alternatives

* Recommendation or decision state: Prioritize P0 production safety configuration and release gating, then P1 evaluation and output safety, P2 pre-PHI hardening, P3 roadmap capabilities.
* Rationale: P0 items are low effort and close the largest gap between what the code can do and what production runs (C1-C6). Capability work is worth more on a trustworthy, gated baseline.
* What could change this result: Evidence that production config is injected externally with these flags, or that `prd` is protected by required checks.

| Priority | Improvement | Effort | Risk reduced | Evidence |
|----------|-------------|--------|--------------|----------|
| P0 | Set `HITL_ENABLED`, `AUDIT_FAIL_CLOSED`, Postgres checkpoint URI (secret) and `LANGGRAPH_CHECKPOINT_REQUIRED=true` in `values-production.yaml`; fail startup if HITL is on without a durable checkpointer | S | Lost reviews, unaudited answers | C1-C4 |
| P0 | Gate the prod deploy on CI (reusable workflow or `workflow_run`) including tests, evals and helm template | S | Unvalidated releases | C5, C6 |
| P0 | Default `PATIENT_SCOPE_AUTH_REQUIRED` to true with explicit dev opt-out | S | Fail-open authorization | C11 |
| P1 | Expand eval set (clinical golden, contraindication, adversarial); add claim-level factuality and safety-caveat gates with higher thresholds; run against the live graph with a stub or recorded model | M | Silent clinical regressions | C7-C9 |
| P1 | Add model-based or classifier output checks plus deterministic rules for dosing and stop-medication directives | M | Harmful output | C10 |
| P2 | Redact PHI in spans and logs; durable tamper-evident audit sink; rate limiting; JWT validation of caller identity | M | PHI leakage, abuse | C4, C12, C13 |
| P3 | Specialist output verification, inter-agent communication, self-critique, clinical NER, cross-encoder rerank, outcome learning | L | Capability | C14, C15 |

| Option | Benefits | Costs and risks | Evidence | Disposition |
|--------|----------|-----------------|----------|-------------|
| Config and gates first | Fast, low-risk, unlocks safe feature work | Does not add capability | C1-C6 | selected |
| Follow docs/10 roadmap order | Matches maintainers' plan | Leaves prod controls off and releases ungated | C14 | rejected as lead; factuality kept at P1 |

## Scope and Questions

* Goal: Identify and prioritize improvements to the healthcare domain AI system.
* Audience and use: Maintainers planning next work.
* In scope: `domains/healthcare/**`, `packages/agent-core`, `.github/workflows`, `infra/helm`, `docs/`.
* Out of scope: supply-chain domain, running the system, live provider behavior, formal HIPAA audit.
* Decision and evidence criteria: patient-safety and data-protection risk, effort, and whether capability already exists.
* Requested output: prioritized improvement list.

| ID | Question | Source | Status |
|----|----------|--------|--------|
| Q1 | What does the repo itself say is missing? | inferred | answered |
| Q2 | Are safety controls enabled where it matters (production)? | inferred | answered |
| Q3 | Do release and evaluation gates protect quality? | inferred | answered |
| Q4 | Are guardrails, identity and data handling adequate for clinical use? | inferred | answered |

## Decisions and Feedback

| Group | Decision or feedback item | Status | Owner | Rationale or input needed | Evidence | Impact of answer |
|-------|---------------------------|--------|-------|---------------------------|----------|------------------|
| D1 | Is production configured outside this repo (external secrets, gateway, branch protection)? | input requested | user | Would turn P0 items into verification tasks | C2, C5 | Changes P0 scope |

## Risks and Open Questions

| Priority | Type | Risk, question, or research item | Impact | Smallest action or evidence needed | Owner |
|----------|------|----------------------------------|--------|------------------------------------|-------|
| H | open question | Production runtime config source | Re-ranks P0 | Confirm deployed env vars | user |
| M | further research | Baseline test and eval run not executed | Validates P1 | `make test-unit` and eval gate | downstream |
| M | further research | Rate limiting at ingress/gateway | Confirms P2 | Review ingress config | research |

## Planning Readiness and Next Step

| Field | Record |
|-------|--------|
| Research disposition | executed |
| Decision participation | user-owned (standalone); D1 is non-blocking input |
| Planning Readiness | Ready for P0-P1 (C1-C10); D1 may refine scope |
| Research depth and helpers | One cycle with all three waves; no helpers |
| Blockers | none |
| Output mode and planning support | convergence; supports planning |
| Continuation owner | user |
| Required gates or confirmations | none |
| Next action | `/rpi-plan` for P0 items |
| Primary evidence file | `.copilot-tracking/research/2026-10-23/healthcare-ai-improvement-priorities-research.md` (current date) |

## Research Record

### Method and Boundaries

| Field | Record |
|-------|--------|
| Research posture and provenance | balanced; default |
| Completion basis | Material claims backed by file evidence; contrarian checks done |
| Explicit limits or deadline | none |
| Codebase and external scope | healthcare domain and shared packages; no external sources |
| Evidence root | `.copilot-tracking/research/` default |
| Prior knowledge | none; no prior artifacts |

### Extensions and Participation

| Kind | Candidate | Provenance | Reason |
|------|-----------|------------|--------|
| instruction | governed-ai-engineering (applyTo `**`) | matched | selected: shaped criteria (authorization, audit, HITL, PHI) |
| skill | none relevant | n/a | skipped |

No intake questions were needed.

### Research Cycle Log

#### Cycle 1

* Wave 1 Wider: surveyed docs, workflows, Helm values, source layout; found the repo's self-assessed roadmap (C14).
* Wave 2 Deeper: inspected auth, checkpointer, guardrails, eval gates, audit, tracing (C1-C13).
* Wave 3 Contrarian: looked for mitigations. Prod sets patient-scope auth and role header off (partially mitigates auth, C11). Dev sets HITL and audit but prod does not (C2, C3). No deploy gating found (C5).
* Synthesis: all findings accepted; "shared checkpointer" reclassified from build to enable (C1). Another cycle: no; sources saturated.

### Evidence Log

| ID | Claim or finding | Source or location | Retrieved | Tool | Confidence |
|----|------------------|--------------------|-----------|------|------------|
| C1 | `get_checkpointer` falls back to `InMemorySaver` unless required flag set | `domains/healthcare/agent-service/src/healthcare_agent/orchestration/hitl.py` `get_checkpointer` | not applicable | read | high |
| C2 | Prod values set role-header off and patient-scope on; no HITL, audit or checkpoint keys | `infra/helm/values-production.yaml` agent-service config | not applicable | grep, read | high |
| C3 | Dev values set `AUDIT_FAIL_CLOSED`, `HITL_ENABLED`, `LANGGRAPH_CHECKPOINT_REQUIRED` | `infra/helm/values-dev.yaml` | not applicable | grep | high |
| C4 | `audit_fail_closed` default False; audit is local JSONL | `packages/agent-core/src/agent_core/settings.py`; `packages/agent-core/src/agent_core/audit.py` `JsonlAuditSink` | not applicable | read | high |
| C5 | Deploy triggers on `prd` push, single job, no `needs` | `.github/workflows/deploy-ai-prd.yml` | not applicable | read | high |
| C6 | CI triggers only on `dev`; gate runs a static results file with `--min-score 0.5` | `.github/workflows/agent-service-contracts.yml` | not applicable | read | high |
| C7 | Gate thresholds 0.5-0.6 over routing, evidence, answer only | `domains/healthcare/agent-service/src/healthcare_agent/evaluation/gates.py` `GateThresholds` | not applicable | read | high |
| C8 | Fixtures: 5 result rows, 12 planner cases | `domains/healthcare/agent-service/tests/evals/fixtures/` | not applicable | read | high |
| C9 | Retrieval benchmark has 25 cases | `domains/healthcare/agent-service/src/healthcare_agent/evaluation/fixtures/retrieval_benchmark.json` | not applicable | read | high |
| C10 | Regex-based input and output guardrails | `domains/healthcare/agent-service/src/healthcare_agent/safety/guardrails.py` `classify_output` | not applicable | read | high |
| C11 | `patient_scope_auth_required` default False; fail-closed authorizer when true | `domains/healthcare/agent-service/src/healthcare_agent/config/settings.py`; `api/patient_scope.py` | not applicable | read | high |
| C12 | MLflow span inputs include raw question and patient_id | `domains/healthcare/agent-service/src/healthcare_agent/observability/tracing.py` | not applicable | read | high |
| C13 | Caller identity from `X-Caller-Id` header; no rate-limit code found | `domains/healthcare/agent-service/src/healthcare_agent/api/routes.py`; grep | not applicable | read, grep | medium |
| C14 | Roadmap and gap list | `docs/10_healthcare_landscape.md` sections 5-6 | not applicable | read | high |
| C15 | `fusion_rerank` is score fusion, not a cross-encoder | `domains/healthcare/agent-service/src/healthcare_agent/retrieval/ranking.py` `fusion_rerank` | not applicable | grep | medium |

Contradictions and conflicts: none. Helpers: none.

### Artifact Self-Check

* Checked sections: all user-facing sections, evidence log, cycle log.
* Missing or limited sections: no tests executed; no external sources; D1 unanswered.
