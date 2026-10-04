# Healthcare Provider Web UI

React 19 + TypeScript single-page app (built with Vite) for the Healthcare Hybrid GraphRAG API.
It is decision support only. Clinical review is required before anyone acts on its results.

## Features

- **RAG query mode** calls `POST /query`, with optional patient scope and a structured clinical summary:
  - confidence
  - risk severity counts
  - key findings
  - medication interactions and lab signals
  - safety caveat
  - guardrail input/output block alerts
- **MCP tools mode** calls the 11 server tools over MCP streamable HTTP (`POST /mcp`):
  - performs the initialize → initialized → `tools/call` handshake and session teardown
  - renders a typed form per tool, validated against server enums
  - patient-memory writes require the governed `memory_write` role and explicit consent
- **Evidence explorer**: search, type filter, sorting, score bars and a redaction notice.
- **Knowledge-graph view**:
  - SVG graph of `graph_context` with a legend
  - toggles per node kind
  - hover to highlight neighbours
  - click a node to see its details
  - edges for interactions, contraindications, lab signals and adverse events
- **Trace view**: retrieval plan, guardrails, model routing, ReAct steps and raw JSON.
- **Multi-turn session**:
  - a `session_id` is sent so the backend session memory applies
  - re-run, cancel (Esc), remove and new session
  - export each result as Markdown or JSON
- API/MCP health indicators, light/dark theme, keyboard submit (⌘/Ctrl + Enter).

**Privacy:** questions and answers stay in memory for the tab. Only the API base URL, mode and theme are stored in `localStorage`.

## Layout

| Path | Purpose |
| --- | --- |
| `src/api/` | Transport only: `client.ts` (the single `fetch` caller, with timeout/cancel), SSE parser, wire types and guards, MCP tool catalog |
| `src/lib/` | Pure logic: conversation reducer, graph builder/layout, exporters, formatting |
| `src/hooks/` | Health polling, conversation orchestration, persisted settings |
| `src/components/` | UI views |

## Development

```bash
npm install
cp .env.example .env.local        # optional
VITE_API_BASE_URL=/api npm run dev # http://localhost:5173, proxies /api -> VITE_API_PROXY_TARGET
```

With `VITE_API_BASE_URL=/api`, the Vite dev proxy forwards requests to the API (default `http://localhost:8000`), so no CORS changes are needed. The API base URL can also be changed at runtime in the sidebar.

```bash
npm run typecheck
npm test          # vitest unit tests (src/**/*.test.ts)
npm run build     # tsc + vite build -> dist/
```

Make targets from the repo root: `make web-hc-dev`, `make web-hc-test`, `make web-hc-build`.

## Container

The `Dockerfile` is multi-stage and uses the repository root as build context. It runs the tests and builds with Node 22, then serves `dist/` with Nginx using `infra/web/nginx.conf` (with SPA fallback).

```bash
docker build -f domains/healthcare/webapp/Dockerfile \
  --build-arg VITE_API_BASE_URL=http://localhost:8000 -t provider-web .
```

## Notes

- FastMCP's DNS-rebinding protection accepts only `localhost`/`127.0.0.1` Host and Origin headers by default. Deployments behind other hostnames need `allowed_hosts`/`allowed_origins` configured on the server before MCP mode will work there.
