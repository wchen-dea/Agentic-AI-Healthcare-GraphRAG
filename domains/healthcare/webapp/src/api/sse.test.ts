import { describe, expect, it } from "vitest";
import { createSseParser, parseEventJson } from "./sse";

describe("createSseParser", () => {
  it("parses events split across arbitrary chunk boundaries", () => {
    const p = createSseParser();
    const out = [...p.push("event: mess"), ...p.push("age\ndata: {\"a\""), ...p.push(":1}\n\n")];
    expect(out).toEqual([{ event: "message", data: '{"a":1}' }]);
  });

  it("handles CRLF split between chunks without emitting a phantom event", () => {
    const p = createSseParser();
    const out = [...p.push("data: x\r"), ...p.push("\n\r"), ...p.push("\ndata: y\r\n\r\n")];
    expect(out.map((e) => e.data)).toEqual(["x", "y"]);
  });

  it("joins multi-line data and ignores comments", () => {
    const p = createSseParser();
    expect(p.push(": ping\ndata: a\ndata: b\n\n")).toEqual([{ data: "a\nb" }]);
  });

  it("scopes ids to the event that declared them", () => {
    const p = createSseParser();
    const out = p.push("id: 1\ndata: first\n\ndata: second\n\n");
    expect(out[0]?.id).toBe("1");
    expect(out[1]?.id).toBeUndefined();
  });

  it("flushes a trailing event on end()", () => {
    const p = createSseParser();
    expect(p.push("data: tail")).toEqual([]);
    expect(p.end()).toEqual([{ data: "tail" }]);
  });

  it("returns undefined for malformed JSON", () => {
    expect(parseEventJson({ data: "{oops" })).toBeUndefined();
    expect(parseEventJson({ data: "[1]" })).toEqual([1]);
  });
});
