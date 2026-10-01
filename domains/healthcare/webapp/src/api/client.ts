// Transport layer: the only module that calls fetch().
import { config, normalizeBaseUrl } from "../config";
import { errorDetail, isRecord, parseAgents, parseAgentStep, parseQueryResponse } from "./guards";
import { createSseParser, parseEventJson } from "./sse";
import type { AgentCard, AgentProgressStep, HealthStatus, QueryRequest, QueryResponse } from "./types";
import type { ToolArgs } from "./tools";

export type ApiErrorKind = "http" | "timeout" | "cancelled" | "network" | "protocol";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;

  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
  }
}

export interface RequestHandle<T> {
  promise: Promise<T>;
  cancel: () => void;
}

/** One AbortController backs both the timeout and user cancellation. */
function withAbort<T>(run: (signal: AbortSignal) => Promise<T>, timeoutMs = config.requestTimeoutMs): RequestHandle<T> {
  const controller = new AbortController();
  let reason: "timeout" | "cancelled" | undefined;
  const timer = setTimeout(() => {
    reason = "timeout";
    controller.abort();
  }, timeoutMs);

  const promise = run(controller.signal)
    .catch((err: unknown) => {
      if (controller.signal.aborted) {
        throw reason === "timeout"
          ? new ApiError("timeout", `Request timed out after ${Math.round(timeoutMs / 1000)}s.`)
          : new ApiError("cancelled", "Request cancelled.");
      }
      if (err instanceof ApiError) throw err;
      throw new ApiError("network", err instanceof Error ? err.message : "Network error.");
    })
    .finally(() => clearTimeout(timer));

  return {
    promise,
    cancel: () => {
      reason = "cancelled";
      controller.abort();
    },
  };
}

async function readJsonSafe(response: Response): Promise<unknown> {
  const text = await response.text();
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

async function ensureOk(response: Response): Promise<void> {
  if (response.ok) return;
  const body = await readJsonSafe(response);
  const detail = errorDetail(body) ?? (typeof body === "string" ? body.slice(0, 300) : "");
  throw new ApiError("http", `HTTP ${response.status}${detail ? `: ${detail}` : ""}`, response.status);
}

export function runRagQuery(apiBase: string, payload: QueryRequest): RequestHandle<QueryResponse> {
  return withAbort(async (signal) => {
    const response = await fetch(`${normalizeBaseUrl(apiBase)}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
    await ensureOk(response);
    return parseQueryResponse(await response.json());
  });
}

export type StepListener = (step: AgentProgressStep) => void;

/**
 * Consume a `/query/stream` body: `meta`, `step`*, then exactly one `result` or `error`.
 * Step events are forwarded to `onStep`; the result is narrowed like `/query`.
 */
export async function readQueryStream(response: Response, onStep: StepListener): Promise<QueryResponse> {
  if (!response.body) throw new ApiError("protocol", "Stream response had no body.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser();
  const seen = new Set<string>();

  const handle = (events: ReturnType<typeof parser.push>): QueryResponse | undefined => {
    for (const evt of events) {
      if (evt.id) {
        if (seen.has(evt.id)) continue;
        seen.add(evt.id);
      }
      const json = parseEventJson(evt);
      if (evt.event === "step") {
        const step = parseAgentStep(json);
        if (step) onStep(step);
      } else if (evt.event === "result") {
        return parseQueryResponse(json);
      } else if (evt.event === "error") {
        throw new ApiError("protocol", errorDetail(json) ?? "Query failed.");
      }
    }
    return undefined;
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const result = handle(parser.push(decoder.decode(value, { stream: true })));
      if (result) return result;
    }
    const result = handle(parser.end());
    if (result) return result;
  } finally {
    reader.cancel().catch(() => undefined);
  }
  throw new ApiError("protocol", "Stream ended before a result was received.");
}

export function streamRagQuery(apiBase: string, payload: QueryRequest, onStep: StepListener): RequestHandle<QueryResponse> {
  return withAbort(async (signal) => {
    const response = await fetch(`${normalizeBaseUrl(apiBase)}/query/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(payload),
      signal,
    });
    await ensureOk(response);
    return readQueryStream(response, onStep);
  });
}

/** True when the server predates `/query/stream`, so the caller should use `/query`. */
export function isStreamUnsupported(err: unknown): boolean {
  return err instanceof ApiError && err.kind === "http" && (err.status === 404 || err.status === 405);
}

/** Stream agent progress, falling back to the synchronous `/query` once if streaming is unavailable. */
export function runRagQueryStreaming(
  apiBase: string,
  payload: QueryRequest,
  onStep: StepListener,
  onUnsupported: () => void = () => undefined,
): RequestHandle<QueryResponse> {
  let current = streamRagQuery(apiBase, payload, onStep);
  let cancelled = false;
  const promise = current.promise.catch((err: unknown) => {
    if (cancelled || !isStreamUnsupported(err)) throw err;
    onUnsupported();
    current = runRagQuery(apiBase, payload);
    return current.promise;
  });
  return {
    promise,
    cancel: () => {
      cancelled = true;
      current.cancel();
    },
  };
}

export function checkHealth(apiBase: string): RequestHandle<HealthStatus> {
  return withAbort(async (signal) => {
    const base = normalizeBaseUrl(apiBase);
    const [api, mcp] = await Promise.allSettled([
      fetch(`${base}/health`, { signal }),
      fetch(`${base}/mcp/health`, { signal }),
    ]);
    return {
      api: api.status === "fulfilled" && api.value.ok ? "ok" : "error",
      mcp: mcp.status === "fulfilled" ? (mcp.value.ok ? "ok" : "error") : "unknown",
      checkedAt: new Date().toISOString(),
    };
  }, 10_000);
}

export function getAgents(apiBase: string): RequestHandle<AgentCard[]> {
  return withAbort(async (signal) => {
    const response = await fetch(`${normalizeBaseUrl(apiBase)}/agents`, { signal });
    await ensureOk(response);
    return parseAgents(await readJsonSafe(response));
  }, 10_000);
}

// ---------------- MCP (streamable HTTP) ----------------

const MCP_ACCEPT = "application/json, text/event-stream";

/** Read a JSON-RPC response with the given id from a JSON or SSE body. */
export async function readJsonRpcResponse(response: Response, id: string): Promise<Record<string, unknown>> {
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("text/event-stream")) {
    const body = await readJsonSafe(response);
    if (isRecord(body)) return body;
    throw new ApiError("protocol", "MCP response was not a JSON-RPC object.");
  }
  if (!response.body) throw new ApiError("protocol", "MCP response had no body.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const parser = createSseParser();
  const seen = new Set<string>();

  const match = (events: ReturnType<typeof parser.push>): Record<string, unknown> | undefined => {
    for (const evt of events) {
      if (evt.id) {
        if (seen.has(evt.id)) continue;
        seen.add(evt.id);
      }
      const json = parseEventJson(evt);
      if (isRecord(json) && json.id === id) return json;
    }
    return undefined;
  };

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      const found = match(parser.push(decoder.decode(value, { stream: true })));
      if (found) return found;
    }
    const found = match(parser.end());
    if (found) return found;
  } finally {
    reader.cancel().catch(() => undefined);
  }
  throw new ApiError("protocol", "MCP stream ended before a response was received.");
}

/** FastMCP returns either structuredContent or JSON text content. */
export function normalizeMcpResult(result: unknown): unknown {
  if (!isRecord(result)) return {};
  if (result.isError === true) {
    const text = Array.isArray(result.content)
      ? result.content.filter(isRecord).map((c) => (typeof c.text === "string" ? c.text : "")).join("\n")
      : "";
    throw new ApiError("protocol", text || "MCP tool returned an error.");
  }
  const structured = result.structuredContent;
  if (isRecord(structured)) {
    const keys = Object.keys(structured);
    return keys.length === 1 && keys[0] === "result" && isRecord(structured.result) ? structured.result : structured;
  }
  if (Array.isArray(result.content)) {
    const text = result.content
      .filter(isRecord)
      .map((c) => (c.type === "text" && typeof c.text === "string" ? c.text : ""))
      .join("\n")
      .trim();
    if (text) {
      try {
        return JSON.parse(text) as unknown;
      } catch {
        return { answer: text };
      }
    }
  }
  return result;
}

function rpcError(json: Record<string, unknown>): string | undefined {
  const err = json.error;
  if (!isRecord(err)) return undefined;
  return typeof err.message === "string" ? err.message : "Unknown MCP error.";
}

export function runMcpTool(apiBase: string, toolName: string, args: ToolArgs): RequestHandle<QueryResponse> {
  return withAbort(async (signal) => {
    const endpoint = `${normalizeBaseUrl(apiBase)}/mcp`;
    const post = (body: unknown, sessionId?: string) =>
      fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: MCP_ACCEPT,
          ...(sessionId ? { "Mcp-Session-Id": sessionId } : {}),
        },
        body: JSON.stringify(body),
        signal,
      });

    const initResp = await post({
      jsonrpc: "2.0",
      id: "init-1",
      method: "initialize",
      params: { protocolVersion: config.mcpProtocolVersion, capabilities: {}, clientInfo: config.mcpClientInfo },
    });
    await ensureOk(initResp);
    const sessionId = initResp.headers.get("mcp-session-id") ?? undefined;
    const initJson = await readJsonRpcResponse(initResp, "init-1");
    const initErr = rpcError(initJson);
    if (initErr) throw new ApiError("protocol", `MCP initialize failed: ${initErr}`);

    const notify = await post({ jsonrpc: "2.0", method: "notifications/initialized", params: {} }, sessionId);
    await notify.body?.cancel().catch(() => undefined);

    const callResp = await post(
      { jsonrpc: "2.0", id: "call-1", method: "tools/call", params: { name: toolName, arguments: args } },
      sessionId,
    );
    await ensureOk(callResp);
    const callJson = await readJsonRpcResponse(callResp, "call-1");
    const callErr = rpcError(callJson);
    if (callErr) throw new ApiError("protocol", `MCP tool error: ${callErr}`);

    if (sessionId) {
      // Best-effort session teardown; never block the result on it.
      fetch(endpoint, { method: "DELETE", headers: { "Mcp-Session-Id": sessionId } }).catch(() => undefined);
    }
    return parseQueryResponse(normalizeMcpResult(callJson.result));
  });
}
