import { afterEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  normalizeMcpResult,
  readJsonRpcResponse,
  readQueryStream,
  runRagQueryStreaming,
} from "./client";
import type { AgentProgressStep } from "./types";

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return new Response(body, { headers: { "content-type": "text/event-stream" } });
}

describe("readJsonRpcResponse", () => {
  it("finds the matching id in a chunked SSE body", async () => {
    const resp = sseResponse([
      'event: message\ndata: {"jsonrpc":"2.0","method":"notifications/progress"}\n\n',
      'event: message\ndata: {"jsonrpc":"2.0","id":"call-1",',
      '"result":{"ok":true}}\n\n',
    ]);
    const json = await readJsonRpcResponse(resp, "call-1");
    expect(json.result).toEqual({ ok: true });
  });

  it("reads plain JSON bodies", async () => {
    const resp = new Response(JSON.stringify({ id: "x", result: 1 }), {
      headers: { "content-type": "application/json" },
    });
    expect((await readJsonRpcResponse(resp, "x")).result).toBe(1);
  });

  it("throws a protocol error when the stream ends without a match", async () => {
    await expect(readJsonRpcResponse(sseResponse(["data: {}\n\n"]), "nope")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("normalizeMcpResult", () => {
  it("parses JSON text content", () => {
    expect(normalizeMcpResult({ content: [{ type: "text", text: '{"answer":"hi"}' }] })).toEqual({ answer: "hi" });
  });

  it("wraps non-JSON text as an answer", () => {
    expect(normalizeMcpResult({ content: [{ type: "text", text: "plain" }] })).toEqual({ answer: "plain" });
  });

  it("unwraps structuredContent.result", () => {
    expect(normalizeMcpResult({ structuredContent: { result: { a: 1 } } })).toEqual({ a: 1 });
  });

  it("throws on tool errors", () => {
    expect(() => normalizeMcpResult({ isError: true, content: [{ type: "text", text: "denied" }] })).toThrow("denied");
  });
});

const stepEvent = (id: number, node: string) =>
  `id: ${id}\nevent: step\ndata: ${JSON.stringify({ node, messages: [{ agent: node, action: "done" }] })}\n\n`;

describe("readQueryStream", () => {
  it("forwards steps then returns the narrowed result", async () => {
    const steps: AgentProgressStep[] = [];
    const resp = sseResponse([
      `event: meta\ndata: {"trace_id":"t","orchestrator":"langgraph"}\n\n`,
      stepEvent(1, "input_guardrail"),
      stepEvent(1, "input_guardrail"),
      stepEvent(2, "tri"),
      `id: 3\nevent: result\ndata: {"answer":"ok","trace_id":"t"}\n\n`,
    ]);
    const result = await readQueryStream(resp, (s) => steps.push(s));
    expect(result.answer).toBe("ok");
    expect(steps.map((s) => s.node)).toEqual(["input_guardrail", "tri"]);
  });

  it("raises a protocol error for an error event", async () => {
    const resp = sseResponse([`event: error\ndata: {"detail":"Query failed (RuntimeError).","trace_id":"t"}\n\n`]);
    await expect(readQueryStream(resp, () => undefined)).rejects.toMatchObject({
      kind: "protocol",
      message: "Query failed (RuntimeError).",
    });
  });

  it("raises when the stream ends without a result", async () => {
    await expect(readQueryStream(sseResponse([stepEvent(1, "triage")]), () => undefined)).rejects.toBeInstanceOf(
      ApiError,
    );
  });
});

describe("runRagQueryStreaming", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("falls back to /query once when streaming is unavailable", async () => {
    const fetchMock = vi.fn(async (url: string) =>
      url.endsWith("/query/stream")
        ? new Response("Not Found", { status: 404 })
        : new Response(JSON.stringify({ answer: "sync" }), { headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const onUnsupported = vi.fn();
    const result = await runRagQueryStreaming("http://api", { question: "q" }, () => undefined, onUnsupported).promise;
    expect(result.answer).toBe("sync");
    expect(onUnsupported).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(["http://api/query/stream", "http://api/query"]);
  });

  it("does not fall back on authorization failures", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ detail: "denied" }), { status: 401 })));
    const onUnsupported = vi.fn();
    await expect(
      runRagQueryStreaming("http://api", { question: "q" }, () => undefined, onUnsupported).promise,
    ).rejects.toMatchObject({ kind: "http", status: 401 });
    expect(onUnsupported).not.toHaveBeenCalled();
  });
});
