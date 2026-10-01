import { describe, expect, it } from "vitest";
import { errorDetail, parseAgentStep, parseQueryResponse, parseStructured, toSeverity } from "./guards";

describe("parseQueryResponse", () => {
  it("tolerates non-object input", () => {
    const r = parseQueryResponse(null);
    expect(r.answer).toBe("");
    expect(r.vector_context).toEqual([]);
    expect(r.graph_context).toEqual([]);
  });

  it("maps known fields and keeps unknown ones in extra", () => {
    const r = parseQueryResponse({
      answer: "ok",
      trace_id: "t-1",
      patients: ["p1", 3],
      vector_context: [{ event_id: "e1", score: 0.9 }, "bad"],
      guardrails: { input_blocked: true, category: "prompt_injection" },
      risk_score: 0.7,
    });
    expect(r.answer).toBe("ok");
    expect(r.trace_id).toBe("t-1");
    expect(r.patients).toEqual(["p1"]);
    expect(r.vector_context).toHaveLength(1);
    expect(r.guardrails?.input_blocked).toBe(true);
    expect(r.extra).toEqual({ risk_score: 0.7 });
  });

  it("falls back to summary when answer is missing", () => {
    expect(parseQueryResponse({ summary: "s" }).answer).toBe("s");
  });

  it("parses the langgraph agent trace", () => {
    const r = parseQueryResponse({
      answer: "ok",
      langgraph: {
        enabled: true,
        iterations: 2,
        confidence: 0.9,
        final_reason: "confidence_reached",
        agent_trace: [{ agent: "triage", action: "classify" }, "bad"],
      },
    });
    expect(r.langgraph?.enabled).toBe(true);
    expect(r.langgraph?.agent_trace).toEqual([{ agent: "triage", action: "classify" }]);
    expect(r.extra.langgraph).toBeUndefined();
  });
});

describe("parseStructured", () => {
  it("normalizes severities and drops non-string findings", () => {
    const s = parseStructured({
      summary: "x",
      key_findings: ["a", 1],
      risks: [{ category: "renal", severity: "HIGH", description: "d" }],
      interactions: [{ drug_a: "A", drug_b: "B", severity: "weird" }],
      confidence: 0.8,
    });
    expect(s?.key_findings).toEqual(["a"]);
    expect(s?.risks[0]?.severity).toBe(toSeverity("high"));
    expect(s?.interactions[0]?.severity).toBe("unknown");
    expect(s?.confidence).toBe(0.8);
  });

  it("returns undefined for non-objects", () => {
    expect(parseStructured("nope")).toBeUndefined();
  });
});

describe("errorDetail", () => {
  it("reads string and validation-array details", () => {
    expect(errorDetail({ detail: "Forbidden" })).toBe("Forbidden");
    expect(errorDetail({ detail: [{ msg: "too short" }, { msg: "bad id" }] })).toBe("too short; bad id");
    expect(errorDetail({})).toBeUndefined();
  });
});

describe("parseAgentStep", () => {
  it("accepts a node with message objects and drops malformed messages", () => {
    expect(parseAgentStep({ node: "triage", messages: [{ action: "x" }, "bad", null] })).toEqual({
      node: "triage",
      messages: [{ action: "x" }],
    });
  });

  it("rejects values without a node name", () => {
    expect(parseAgentStep({ messages: [] })).toBeUndefined();
    expect(parseAgentStep("triage")).toBeUndefined();
  });
});
