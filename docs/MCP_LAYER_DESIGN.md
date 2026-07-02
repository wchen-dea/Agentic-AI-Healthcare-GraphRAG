# MCP Layer Design (Minimal)

## Purpose

This document defines a minimal Model Context Protocol (MCP) layer so AI clients can call a stable healthcare toolset without coupling to internal service details.

Goals:

- Reuse existing FastAPI, Qdrant, Neo4j, and Kafka capabilities.
- Expose a small, auditable, provider-agnostic tool surface.
- Start local-first and evolve to production controls with minimal rework.

## ADR References

- [ADR-0004: Embed FastMCP in rag-api](adrs/0004-embed-fastmcp-in-rag-api.md)
- [ADR-0003: Local-first LLM with provider routing](adrs/0003-local-first-llm-provider-routing.md)

## Architecture Placement

```text
AI Client (Copilot, Claude Desktop, custom agent)
  -> Embedded MCP endpoint in rag-api (/mcp)
  -> Existing services behind rag-api:
     - neo4j (graph context)
     - qdrant (vector context)
     - kafka (optional async task events)
```

Default runtime mode is embedded MCP inside rag-api.
The `mcp-server/` folder remains a standalone reference scaffold for future split-service deployments.

## 1) Minimal Tool List

Use 5 tools to keep scope small while covering high-value workflows.

| Tool Name | Purpose | Backing Service |
| --- | --- | --- |
| `patient_context_get` | Retrieve patient-centric graph context summary | Neo4j via rag-api or direct adapter |
| `vector_evidence_search` | Retrieve top-k vector evidence for question/patient | Qdrant via rag-api or direct adapter |
| `graphrag_answer_generate` | Generate grounded answer from vector + graph evidence | rag-api |
| `risk_summary_generate` | Generate concise risk summary for one patient | rag-api + prompt policy |
| `evidence_bundle_export` | Return traceable evidence bundle for audit/review | rag-api aggregation |

Notes:

- Keep tool names stable; evolve behavior via versioned schemas.
- Add async tools later only if needed (`ai_task_submit`, `ai_task_status_get`).

## 2) Request/Response Schemas

Minimal JSON Schema contracts for v1.

### `patient_context_get`

Request schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["patient_id"],
  "properties": {
    "patient_id": { "type": "string", "minLength": 1 },
    "include_claims": { "type": "boolean", "default": true },
    "include_interactions": { "type": "boolean", "default": true }
  },
  "additionalProperties": false
}
```

Response schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["patient_id", "graph_context", "retrieved_at"],
  "properties": {
    "patient_id": { "type": "string" },
    "graph_context": { "type": "array", "items": { "type": "object" } },
    "retrieved_at": { "type": "string", "format": "date-time" },
    "trace_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

### `vector_evidence_search`

Request schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question"],
  "properties": {
    "question": { "type": "string", "minLength": 3 },
    "patient_id": { "type": ["string", "null"] },
    "top_k": { "type": "integer", "minimum": 1, "maximum": 20, "default": 5 }
  },
  "additionalProperties": false
}
```

Response schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question", "vector_context", "retrieved_at"],
  "properties": {
    "question": { "type": "string" },
    "vector_context": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["event_id", "score"],
        "properties": {
          "event_id": { "type": "string" },
          "patient_id": { "type": ["string", "null"] },
          "event_type": { "type": ["string", "null"] },
          "score": { "type": "number" },
          "text": { "type": ["string", "null"] }
        },
        "additionalProperties": true
      }
    },
    "retrieved_at": { "type": "string", "format": "date-time" },
    "trace_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

### `graphrag_answer_generate`

Request schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question"],
  "properties": {
    "question": { "type": "string", "minLength": 3 },
    "patient_id": { "type": ["string", "null"] },
    "response_style": { "type": "string", "enum": ["concise", "clinical", "audit"] }
  },
  "additionalProperties": false
}
```

Response schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["answer", "vector_context", "graph_context", "retrieved_at"],
  "properties": {
    "answer": { "type": "string" },
    "patients": { "type": "array", "items": { "type": "string" } },
    "vector_context": { "type": "array", "items": { "type": "object" } },
    "graph_context": { "type": "array", "items": { "type": "object" } },
    "retrieved_at": { "type": "string", "format": "date-time" },
    "trace_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

### `risk_summary_generate`

Request schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["patient_id"],
  "properties": {
    "patient_id": { "type": "string", "minLength": 1 },
    "time_window_hours": { "type": "integer", "minimum": 1, "maximum": 720, "default": 72 }
  },
  "additionalProperties": false
}
```

Response schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["patient_id", "summary", "risk_signals", "retrieved_at"],
  "properties": {
    "patient_id": { "type": "string" },
    "summary": { "type": "string" },
    "risk_signals": { "type": "array", "items": { "type": "string" } },
    "retrieved_at": { "type": "string", "format": "date-time" },
    "trace_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

### `evidence_bundle_export`

Request schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question"],
  "properties": {
    "question": { "type": "string", "minLength": 3 },
    "patient_id": { "type": ["string", "null"] },
    "include_raw_payload": { "type": "boolean", "default": false }
  },
  "additionalProperties": false
}
```

Response schema:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": ["question", "bundle", "retrieved_at"],
  "properties": {
    "question": { "type": "string" },
    "bundle": {
      "type": "object",
      "required": ["vector_evidence", "graph_evidence"],
      "properties": {
        "vector_evidence": { "type": "array", "items": { "type": "object" } },
        "graph_evidence": { "type": "array", "items": { "type": "object" } }
      },
      "additionalProperties": true
    },
    "retrieved_at": { "type": "string", "format": "date-time" },
    "trace_id": { "type": "string" }
  },
  "additionalProperties": false
}
```

## 3) Auth and Audit Model

Minimal model that runs locally and scales to production.

### AuthN/AuthZ

Local demo (embedded mode):

- Run without bearer-token enforcement by default for local simplicity.
- Enforce role-based authorization through a tool policy in embedded rag-api for both `/query` and MCP tool entrypoints.

Optional standalone mode:

- Static API token in MCP server config.
- Optional allowlist of tool names per token.

Production:

- Service-to-service auth with OAuth2 client credentials or workload identity.
- Tool-level authorization policy:
  - `read_only`: patient_context_get, vector_evidence_search
  - `generation`: query, graphrag_answer_generate, risk_summary_generate
  - `export`: evidence_bundle_export
- Environment-scoped policies (`dev`, `stage`, `prod`).

### Audit

Log one structured audit event per tool call:

- `timestamp`
- `trace_id`
- `tool_name`
- `caller_id` (service principal or token id)
- `input_hash` (SHA-256 of normalized request)
- `patient_scope` (explicit IDs or `cohort`)
- `outcome` (`success` or `error`)
- `latency_ms`
- `response_size_bytes`

Do not log raw PHI payloads. Prefer hashes, IDs, and minimal metadata.

### Data Protection Controls

- Redact or tokenize sensitive fields before returning tool output when policy requires.
- Return guardrails metadata that records evidence-access mode and response truncation state.
- Enforce max response sizes and timeouts per tool.
- Add per-tool rate and burst limits.

## 4) Rollout Phases: Local Demo to Production

### Phase 0: Local Design and Contract Freeze

1. Finalize 5-tool contract and JSON schemas in this document.
1. MCP tool surface is implemented in rag-api over the shared query orchestration.
1. Contract tests with static fixtures and CI validation are in place.

Exit criteria:

- All tool schemas validated.
- Basic happy-path tests pass locally.

Current status:

- Completed in current implementation (embedded MCP in rag-api with the 5-tool surface).

### Phase 1: Local Demo Integration

1. Validate initialize handshake against `http://localhost:8000/mcp`.
1. Keep non-protocol diagnostics available at `/mcp/health`.
1. Validate from at least one MCP client.

Exit criteria:

- End-to-end calls from MCP client succeed.
- Trace IDs link MCP calls to API logs.

Current status:

- Completed for local stack (`/mcp` and `/mcp/health` active, smoke test script present).

### Phase 2: Staging Hardening

1. Add centralized auth (service identity).
1. Add policy gates per tool and environment.
1. Add SLO dashboards (latency, error rate, tool call volume).
1. Add resilience controls (timeouts, retries, circuit breaker).

Exit criteria:

- Security review passed.
- SLO monitoring and alerts active.

### Phase 3: Production Launch

1. Enable production identity and secret management.
1. Enable audited tool access with retention policy.
1. Roll out in canary mode to selected clients.
1. Expand tool set only after stability is proven.

Exit criteria:

- Stable error budget.
- Audit completeness verified.
- Operational runbook published.

## Current Implementation Note

The embedded MCP layer in `rag-api/app.py` already ships all five tools and shares the same retrieval + guardrail core used by `POST /query`.
