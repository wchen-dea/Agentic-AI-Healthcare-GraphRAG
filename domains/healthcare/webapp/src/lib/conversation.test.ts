import { describe, expect, it } from "vitest";
import { parseQueryResponse } from "../api/guards";
import { conversationReducer, initialConversation, isBusy, type TurnRequest } from "./conversation";

const request: TurnRequest = { mode: "rag", question: "q?", patientId: "", structured: false, tool: "query" };

describe("conversationReducer", () => {
  it("tracks pending and success", () => {
    let s = conversationReducer(initialConversation("s1"), { type: "start", id: "t1", request, at: 1 });
    expect(isBusy(s)).toBe(true);
    s = conversationReducer(s, { type: "succeed", id: "t1", response: parseQueryResponse({ answer: "a" }), at: 2 });
    expect(isBusy(s)).toBe(false);
    expect(s.turns[0]).toMatchObject({ status: "success", finishedAt: 2 });
  });

  it("ignores late results after cancellation", () => {
    let s = conversationReducer(initialConversation("s1"), { type: "start", id: "t1", request, at: 1 });
    s = conversationReducer(s, { type: "fail", id: "t1", status: "cancelled", error: "Cancelled", at: 2 });
    const after = conversationReducer(s, { type: "succeed", id: "t1", response: parseQueryResponse({}), at: 3 });
    expect(after).toBe(s);
    expect(after.turns[0]?.status).toBe("cancelled");
  });

  it("appends streamed progress only while pending", () => {
    const step = { node: "triage", messages: [{ agent: "triage", action: "classified" }] };
    let s = conversationReducer(initialConversation("s1"), { type: "start", id: "t1", request, at: 1 });
    s = conversationReducer(s, { type: "progress", id: "t1", step });
    s = conversationReducer(s, { type: "progress", id: "t1", step: { ...step, node: "retrieval" } });
    expect(s.turns[0]?.steps?.map((x) => x.node)).toEqual(["triage", "retrieval"]);
    s = conversationReducer(s, { type: "succeed", id: "t1", response: parseQueryResponse({ answer: "a" }), at: 2 });
    expect(conversationReducer(s, { type: "progress", id: "t1", step })).toBe(s);
  });

  it("removes and resets", () => {
    let s = conversationReducer(initialConversation("s1"), { type: "start", id: "t1", request, at: 1 });
    s = conversationReducer(s, { type: "remove", id: "t1" });
    expect(s.turns).toEqual([]);
    expect(conversationReducer(s, { type: "reset", sessionId: "s2" })).toEqual({ sessionId: "s2", turns: [] });
  });
});
