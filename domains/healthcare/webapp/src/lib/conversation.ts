// Pure state for the multi-turn conversation. No I/O here.
import type { AgentProgressStep, ApiMode, QueryResponse } from "../api/types";

export type TurnStatus = "pending" | "success" | "error" | "cancelled" | "timeout";

export interface TurnRequest {
  mode: ApiMode;
  question: string;
  patientId: string;
  /** RAG only. */
  structured: boolean;
  /** RAG only; maximum evidence items requested from the orchestrator. */
  topK?: number;
}

export interface Turn {
  id: string;
  request: TurnRequest;
  status: TurnStatus;
  startedAt: number;
  finishedAt?: number;
  response?: QueryResponse;
  error?: string;
  /** Live LangGraph node progress received while streaming (RAG only). */
  steps?: AgentProgressStep[];
}

export interface ConversationState {
  sessionId: string;
  turns: Turn[];
}

export type ConversationAction =
  | { type: "start"; id: string; request: TurnRequest; at: number }
  | { type: "progress"; id: string; step: AgentProgressStep }
  | { type: "succeed"; id: string; response: QueryResponse; at: number }
  | { type: "fail"; id: string; status: Exclude<TurnStatus, "pending" | "success">; error: string; at: number }
  | { type: "remove"; id: string }
  | { type: "reset"; sessionId: string };

export function initialConversation(sessionId: string): ConversationState {
  return { sessionId, turns: [] };
}

function update(state: ConversationState, id: string, patch: (t: Turn) => Turn): ConversationState {
  let changed = false;
  const turns = state.turns.map((t) => {
    // Only pending turns can transition; late results for cancelled turns are ignored.
    if (t.id !== id || t.status !== "pending") return t;
    changed = true;
    return patch(t);
  });
  return changed ? { ...state, turns } : state;
}

export function conversationReducer(state: ConversationState, action: ConversationAction): ConversationState {
  switch (action.type) {
    case "start":
      return {
        ...state,
        turns: [...state.turns, { id: action.id, request: action.request, status: "pending", startedAt: action.at }],
      };
    case "progress":
      return update(state, action.id, (t) => ({ ...t, steps: [...(t.steps ?? []), action.step] }));
    case "succeed":
      return update(state, action.id, (t) => ({ ...t, status: "success", response: action.response, finishedAt: action.at }));
    case "fail":
      return update(state, action.id, (t) => ({ ...t, status: action.status, error: action.error, finishedAt: action.at }));
    case "remove":
      return { ...state, turns: state.turns.filter((t) => t.id !== action.id) };
    case "reset":
      return initialConversation(action.sessionId);
  }
}

export function isBusy(state: ConversationState): boolean {
  return state.turns.some((t) => t.status === "pending");
}
