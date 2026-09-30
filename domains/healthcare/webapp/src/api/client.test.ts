import { describe, expect, it } from "vitest";
import { ApiError, normalizeMcpResult, readJsonRpcResponse } from "./client";

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
