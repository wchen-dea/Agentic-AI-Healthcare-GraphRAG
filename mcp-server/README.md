# MCP Server Starter

Minimal MCP adapter layer for this repository.

The default stack now embeds MCP directly into the `rag-api` service at
`http://localhost:8000/mcp`. This folder remains as an optional standalone
scaffold/reference implementation.

This starter exposes five tools from the MCP layer design and routes them to the existing `rag-api` service.

## Implemented Tools

- `patient_context_get`
- `vector_evidence_search`
- `graphrag_answer_generate`
- `risk_summary_generate`
- `evidence_bundle_export`

## Folder Structure

```text
mcp-server/
  app/
    __init__.py
    server.py
    tools.py
    handlers.py
    schemas.py
    auth.py
    audit.py
    config.py
    clients/
      rag_api_client.py
  config/
    tool_policies.json
  logs/
  .env.example
  requirements.txt
```

## Quick Start

1. Create environment variables from `.env.example`.
2. Install dependencies.
3. Run the MCP server entrypoint.

```bash
cd mcp-server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m app.server
```

Run as a standalone container (optional mode):

```bash
cd ..
docker build -f mcp-server/Dockerfile -t healthcare-mcp-server .
docker run --rm -p 8010:8010 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=8010 \
  -e RAG_API_BASE_URL=http://host.docker.internal:8000 \
  healthcare-mcp-server
```

Default MCP endpoint in the project stack (embedded mode):

- <http://localhost:8000/mcp>
- Diagnostic health: <http://localhost:8000/mcp/health>

Standalone scaffold endpoint (optional mode):

- <http://localhost:8010/mcp>

Smoke test the MCP initialize handshake from repo root:

```bash
python3 ./scripts/mcp_smoke_test.py
```

Note: Visiting the MCP protocol endpoint in a browser or plain curl can return
`406` or `400` (for example missing `Accept: text/event-stream` or session
headers). That still confirms the MCP transport is listening.

## Notes

- This is a starter scaffold. Handlers are intentionally minimal but wired end-to-end.
- Tool request and response payloads are validated against JSON schemas in `app/schemas.py`.
- Local auth and tool-level authorization are controlled by `config/tool_policies.json` and environment settings.
