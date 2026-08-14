from __future__ import annotations

import os

import uvicorn

from .tools import mcp


def main() -> None:
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    host = os.getenv("MCP_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_PORT", "8010"))
    mount_path = os.getenv("MCP_MOUNT_PATH", "/mcp")

    if transport == "streamable-http":
        uvicorn.run(mcp.streamable_http_app(), host=host, port=port)
        return

    if transport == "sse":
        uvicorn.run(mcp.sse_app(mount_path=mount_path), host=host, port=port)
        return

    try:
        mcp.run(transport=transport)
    except TypeError:
        # Backward compatibility for SDK variants that only support stdio run().
        mcp.run()


if __name__ == "__main__":
    main()
