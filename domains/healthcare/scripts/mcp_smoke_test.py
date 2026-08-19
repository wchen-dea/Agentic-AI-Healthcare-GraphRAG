#!/usr/bin/env python3
"""Tiny MCP streamable HTTP smoke test.

Performs a real MCP initialize handshake against a streamable HTTP endpoint:
1) POST initialize (expects SSE response + MCP session header)
2) POST notifications/initialized with the returned session header
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_ENDPOINT = "http://localhost:8000/mcp"
DEFAULT_PROTOCOL_VERSION = "2025-03-26"


def post_json(
    endpoint: str,
    payload: dict[str, Any],
    timeout: float,
    session_id: str | None = None,
) -> tuple[int, dict[str, str], str]:
    req = Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    if session_id:
        req.add_header("MCP-Session-Id", session_id)

    with urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, headers, body


def parse_sse_data(body: str) -> dict[str, Any]:
    # FastMCP returns SSE frames where JSON-RPC payload is in "data:" lines.
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: ") :])
    raise ValueError("No SSE data frame found in initialize response")


def fail(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 1


def run(endpoint: str, timeout: float, protocol_version: str) -> int:
    initialize_request = {
        "jsonrpc": "2.0",
        "id": "smoke-init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "repo-smoke-test", "version": "0.1.0"},
        },
    }

    status, headers, body = post_json(endpoint, initialize_request, timeout=timeout)
    if status != 200:
        return fail(f"initialize returned HTTP {status}")

    content_type = headers.get("content-type", "")
    if "text/event-stream" not in content_type.lower():
        return fail(f"initialize expected text/event-stream but got {content_type!r}")

    session_id = headers.get("mcp-session-id")
    if not session_id:
        return fail("initialize response missing mcp-session-id header")

    try:
        init_response = parse_sse_data(body)
    except (ValueError, json.JSONDecodeError) as exc:
        return fail(f"could not parse initialize SSE payload: {exc}")

    result = init_response.get("result", {})
    server_info = result.get("serverInfo", {})
    negotiated_version = result.get("protocolVersion")

    if init_response.get("id") != "smoke-init-1":
        return fail("initialize response id does not match request id")

    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }

    status2, headers2, _ = post_json(
        endpoint,
        initialized_notification,
        timeout=timeout,
        session_id=session_id,
    )
    if status2 not in (200, 202, 204):
        return fail(f"notifications/initialized returned HTTP {status2}")

    if headers2.get("mcp-session-id") != session_id:
        return fail("session id changed or missing on notifications/initialized response")

    print("MCP smoke test passed")
    print(f"- endpoint: {endpoint}")
    print(f"- session_id: {session_id}")
    print(f"- negotiated_protocol_version: {negotiated_version}")
    print(f"- server_name: {server_info.get('name', 'unknown')}")
    print(f"- server_version: {server_info.get('version', 'unknown')}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="MCP initialize handshake smoke test")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("MCP_ENDPOINT", DEFAULT_ENDPOINT),
        help=f"MCP streamable HTTP endpoint (default: {DEFAULT_ENDPOINT})",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds (default: 10)",
    )
    parser.add_argument(
        "--protocol-version",
        default=DEFAULT_PROTOCOL_VERSION,
        help=f"MCP protocolVersion for initialize (default: {DEFAULT_PROTOCOL_VERSION})",
    )
    args = parser.parse_args()

    try:
        return run(args.endpoint, args.timeout, args.protocol_version)
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        return fail(f"HTTP error {exc.code}: {body}")
    except URLError as exc:
        return fail(f"connection error: {exc.reason}")
    except TimeoutError:
        return fail("request timed out")


if __name__ == "__main__":
    raise SystemExit(main())
