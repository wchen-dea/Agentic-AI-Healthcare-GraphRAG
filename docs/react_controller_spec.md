# ReAct Controller Specification

## Purpose

This specification defines a concrete ReAct-style controller for the current GraphRAG runtime.

Design intent:

- keep existing planner, retrieval, and guardrails behavior,
- add an explicit iterative Reason -> Act -> Observe loop,
- keep all outputs policy-shaped and auditable,
- make loop behavior testable with deterministic unit tests.

## Scope

In scope:

- request-time controller state schema,
- loop execution pseudocode,
- stop and recovery criteria,
- test plan mapped to existing test modules.

Out of scope (initial version):

- cross-request long-term memory,
- autonomous background workflows,
- major changes to MCP tool contracts.

## Current File Mapping

Primary implementation and integration touchpoints:

- `rag-api/app.py`
  - request handling and `POST /query`
  - core retrieval path (`run_query`, `vector_context`, `graph_context`)
  - answer synthesis (`ask_ollama`)
  - policy shaping and response budget enforcement
  - audit logging and tool metrics
- `rag-api/domain/planner.py`
  - request classification and retrieval plan selection
- `rag-api/domain/evidence.py`
  - deterministic ranking for vector and graph contexts
- `rag-api/skills_layer.py`
  - business goal to skill/tool resolution
- `rag-api/config/tool_policies.json`
  - role to tool authorization policy
- `rag-api/tests/test_contracts.py`
  - API and tool contract, guardrail, and policy tests
- `rag-api/tests/test_planner_evaluation.py`
  - planner fixture-driven route/plan assertions
- `rag-api/tests/test_planner_edge_cases.py`
  - deterministic planner/ranking edge assertions

Recommended new files:

- `rag-api/domain/react_controller.py`
  - ReAct loop state, policy checks, and execution logic
- `rag-api/tests/test_react_controller.py`
  - deterministic loop tests
- `rag-api/tests/fixtures/react_cases.json`
  - loop scenario fixtures

## Runtime Configuration

Add optional environment settings in `rag-api/app.py` `Settings`:

- `RAG_API_REACT_ENABLED` (default: `false`)
- `RAG_API_REACT_MAX_ITERS` (default: `3`, min: `1`, max: `6`)
- `RAG_API_REACT_MIN_CONFIDENCE` (default: `0.75`, range: `0.0-1.0`)
- `RAG_API_REACT_MAX_NO_PROGRESS_STEPS` (default: `1`)
- `RAG_API_REACT_OBSERVATION_CHAR_BUDGET` (default: `1200`)

Design rule: if `RAG_API_REACT_ENABLED=false`, retain current single-pass behavior.

## State Schema

State is request-scoped only and should not be persisted as mutable memory across requests.

```json
{
  "trace_id": "uuid",
  "started_at": "ISO-8601",
  "caller_role": "generation|read_only|export",
  "question": "string",
  "patient_id": "string|null",
  "request_type": "patient_summary|medication_safety|lab_interpretation|cohort_triage|...",
  "iteration": 0,
  "max_iterations": 3,
  "status": "running|completed|stopped|failed",
  "final_reason": "string|null",
  "confidence": 0.0,
  "no_progress_count": 0,
  "seen_event_ids": [],
  "seen_patient_ids": [],
  "plan_history": [
    {
      "iteration": 0,
      "plan_name": "string",
      "reason": "string",
      "top_k": 5,
      "query_text": "string"
    }
  ],
  "steps": [
    {
      "iteration": 0,
      "thought": "short deterministic rationale",
      "selected_action": "vector_evidence_search|patient_context_get|graphrag_answer_generate|...",
      "action_input": {
        "question": "string",
        "patient_id": "string|null",
        "top_k": 5
      },
      "observation": {
        "vector_hits": 0,
        "graph_patients": 0,
        "new_event_ids": 0,
        "new_patient_ids": 0,
        "error": "string|null"
      },
      "confidence_after": 0.0,
      "stop_candidate": false,
      "stop_reason": "string|null"
    }
  ],
  "aggregated_context": {
    "vector_context": [],
    "graph_context": []
  },
  "guardrails": {
    "evidence_text_redacted": true,
    "evidence_access_level": "none|bounded",
    "graph_access_level": "standard|broader",
    "max_context_items": 5,
    "max_response_bytes": 50000,
    "response_truncated": false,
    "raw_payload_returned": false
  }
}
```

### Notes on schema fields

- `thought` is deterministic and short. Do not store chain-of-thought style private reasoning.
- `selected_action` must be authorized by current role policy before execution.
- `aggregated_context` remains subject to existing response shaping and byte-budget trimming.

## Action Set and Role Constraints

Initial action set should reuse existing runtime call paths:

- `vector_evidence_search` -> calls `vector_context` (+ ranking)
- `patient_context_get` -> calls `graph_context` (+ ranking)
- `graphrag_answer_generate` -> calls synthesis over accumulated evidence
- `skills_plan_get` (optional for business-goal routed flows)

Role policy source of truth remains `rag-api/config/tool_policies.json`.

If an action is not allowed for role:

- record observation error `unauthorized_action`,
- increment `no_progress_count`,
- select next allowed action in same iteration if available,
- otherwise stop with `policy_blocked`.

## Loop Pseudocode

```python
def run_query_react(question: str, patient_id: str | None, caller_role: str) -> dict:
    state = init_state(question, patient_id, caller_role)

    while state.status == "running" and state.iteration < state.max_iterations:
        # Reason
        request_type = classify_request_type(question, patient_id)
        plan = select_retrieval_plan(
            request_type=request_type,
            question=derive_query_text(question, state),
            patient_id=patient_id,
            max_top_k=settings.max_context_items,
        )
        state.plan_history.append(plan_to_record(plan, state.iteration))

        # Act selection (deterministic policy)
        action = choose_action(plan, state)
        if not is_action_authorized(action, caller_role):
            record_policy_block(state, action)
            if should_stop(state):
                break
            continue

        # Act
        result = execute_action(action, plan, question, patient_id, state)

        # Observe
        obs = summarize_observation(result, state)
        append_step(state, action, plan, obs)

        # Aggregate evidence
        merge_context(state.aggregated_context, result)

        # Evaluate confidence/progress
        state.confidence = estimate_confidence(state, obs)
        if obs.new_event_ids == 0 and obs.new_patient_ids == 0:
            state.no_progress_count += 1
        else:
            state.no_progress_count = 0

        # Stop checks
        reason = evaluate_stop_reason(state, obs)
        if reason is not None:
            state.status = "completed"
            state.final_reason = reason
            break

        state.iteration += 1

    if state.status == "running":
        state.status = "stopped"
        state.final_reason = "max_iterations_reached"

    answer = synthesize_answer(
        question=question,
        vector_ctx=state.aggregated_context["vector_context"],
        graph_ctx=state.aggregated_context["graph_context"],
    )

    payload = build_response_payload(state, answer)
    payload = apply_existing_guardrails_and_budget(payload)
    write_audit_event(payload, state)
    return payload
```

### Deterministic choose_action policy (v1)

1. If request type is cohort and no graph context yet -> `patient_context_get`.
2. If no vector evidence yet -> `vector_evidence_search`.
3. If medication safety request and graph context lacks medications/interactions -> `patient_context_get`.
4. If confidence >= threshold and both evidence channels non-empty -> `graphrag_answer_generate`.
5. Otherwise alternate between vector and graph action that produced new evidence last iteration.

## Stop Criteria

Stop checks are evaluated after every observation and before next iteration.

Primary stop reasons:

- `confidence_reached`: `confidence >= RAG_API_REACT_MIN_CONFIDENCE` and both evidence channels non-empty.
- `max_iterations_reached`: `iteration >= RAG_API_REACT_MAX_ITERS`.
- `no_progress_limit`: `no_progress_count > RAG_API_REACT_MAX_NO_PROGRESS_STEPS`.
- `policy_blocked`: no authorized action remains for role.
- `tool_error_budget_exhausted`: repeated action execution errors in same request.
- `response_budget_guard`: predicted response size would exceed `RAG_API_MAX_RESPONSE_BYTES` unless stopped.

Secondary fail-safe behavior:

- On transient action errors, retry once with downgraded action inputs (`top_k` reduced).
- On repeated error, switch to alternate evidence source action.
- If all actions fail, return bounded response with explicit guardrail metadata and `final_reason` set.

## API Contract Changes

Minimal, backward-compatible contract extension for `POST /query` and generation MCP tools:

Add optional `react` block in response:

```json
{
  "react": {
    "enabled": true,
    "iterations": 2,
    "final_reason": "confidence_reached",
    "confidence": 0.82,
    "actions": [
      {"iteration": 0, "action": "vector_evidence_search", "new_event_ids": 4},
      {"iteration": 1, "action": "patient_context_get", "new_patient_ids": 1}
    ]
  }
}
```

Privacy rule: do not return internal `thought` text by default.

## Metrics and Audit Additions

Add optional metrics labels/counters in `rag-api/app.py`:

- `rag_api_react_iterations` (histogram)
- `rag_api_react_stop_total{reason=...}` (counter)
- `rag_api_react_action_total{action=..., outcome=...}` (counter)

Audit event additions:

- `react.enabled`
- `react.iterations`
- `react.final_reason`
- `react.action_trace` (action names and outcome summary only)

## Test Plan Mapped to Current Suite

### 1. Unit tests: new `rag-api/tests/test_react_controller.py`

Core deterministic tests:

1. `test_stops_on_confidence_after_dual_evidence`
- Asserts stop reason `confidence_reached`.

2. `test_stops_on_max_iterations`
- Asserts capped loop and final reason.

3. `test_no_progress_triggers_stop`
- Simulates repeated empty observations.

4. `test_unauthorized_action_causes_policy_block`
- Uses role with restricted tools.

5. `test_error_fallback_switches_action`
- First action fails, second succeeds.

6. `test_response_remains_within_budget_after_loop`
- Verifies byte budget and truncation metadata.

### 2. Contract tests: extend `rag-api/tests/test_contracts.py`

Add focused tests:

1. `test_query_react_block_present_when_enabled`
2. `test_query_react_block_absent_when_disabled`
3. `test_query_react_respects_role_policy`
4. `test_query_react_guardrails_match_existing_defaults`

### 3. Planner tests: optional extension in `rag-api/tests/test_planner_edge_cases.py`

Add action-selection edge assertions:

1. `test_react_choose_action_prefers_missing_channel`
2. `test_react_choose_action_for_medication_safety_prefers_graph_when_interactions_missing`

### 4. Fixtures: new `rag-api/tests/fixtures/react_cases.json`

Fixture fields:

- `id`
- `question`
- `patient_id`
- `mock_vector_result`
- `mock_graph_result`
- `expected_actions`
- `expected_stop_reason`
- `expected_iterations`

## Rollout Plan

Phase 1 (dark launch):

- implement controller module,
- keep `RAG_API_REACT_ENABLED=false` by default,
- run tests in CI.

Phase 2 (limited enablement):

- enable in lower environment,
- capture metrics and audit traces,
- validate no regression on latency and response budget.

Phase 3 (general availability):

- set default on for generation role,
- keep role and policy constraints unchanged,
- publish runbook updates and troubleshooting notes.

## Acceptance Criteria

Functional:

- ReAct loop executes deterministically with bounded iterations.
- Existing single-pass path remains available and unchanged when disabled.
- All role policies and guardrails still apply.

Quality:

- New tests pass plus no regression in existing planner/contract suites.
- Loop stop reasons are observable through metrics and audit logs.
- Response budget trimming remains effective under iterative aggregation.

Operational:

- No new required external dependencies.
- No changes required to existing MCP transport contract.
- Can be rolled back instantly by setting `RAG_API_REACT_ENABLED=false`.
