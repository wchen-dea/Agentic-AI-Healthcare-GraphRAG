import { describe, expect, it } from "vitest";
import { parseQueryResponse } from "../api/guards";
import type { Turn } from "./conversation";
import { turnToJson, turnToMarkdown } from "./export";

const turn: Turn = {
  id: "t1",
  request: { mode: "rag", question: "Risk?", patientId: "patient-0001", structured: true, tool: "query" },
  status: "success",
  startedAt: 0,
  finishedAt: 1000,
  response: parseQueryResponse({
    answer: "Elevated risk.",
    trace_id: "abc",
    vector_context: [{ event_id: "e|1", patient_id: "patient-0001", event_type: "lab", score: 0.5 }],
    structured_response: {
      summary: "s",
      key_findings: ["finding"],
      risks: [{ category: "renal", severity: "high", description: "line1\nline2" }],
      confidence: 0.75,
    },
  }),
};

describe("export", () => {
  it("produces round-trippable JSON", () => {
    const parsed = JSON.parse(turnToJson(turn)) as { status: string; finished_at: string };
    expect(parsed.status).toBe("success");
    expect(parsed.finished_at).toBe("1970-01-01T00:00:01.000Z");
  });

  it("renders markdown with escaped table cells and a safety footer", () => {
    const md = turnToMarkdown(turn);
    expect(md).toContain("**Trace ID:** abc");
    expect(md).toContain("e\\|1");
    expect(md).toContain("line1 line2");
    expect(md).toContain("Clinical review is required");
  });

  it("renders errors", () => {
    expect(turnToMarkdown({ ...turn, response: undefined, status: "error", error: "boom" })).toContain("## Error");
  });
});
