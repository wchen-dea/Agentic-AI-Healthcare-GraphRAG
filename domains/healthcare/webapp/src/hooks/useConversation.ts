import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, runMcpTool, runRagQuery, runRagQueryStreaming, type RequestHandle } from "../api/client";
import type { QueryRequest, QueryResponse } from "../api/types";
import { conversationReducer, initialConversation, isBusy, type TurnRequest } from "../lib/conversation";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export interface ConversationOptions {
  /** Stream LangGraph agent progress from `/query/stream` for RAG turns. */
  stream: boolean;
}

export function useConversation(apiBase: string, { stream }: ConversationOptions = { stream: false }) {
  const [state, dispatch] = useReducer(conversationReducer, undefined, () => initialConversation(newId()));
  const inflight = useRef(new Map<string, RequestHandle<QueryResponse>>());
  // Remember per API base when the server lacks `/query/stream`, to skip the extra round trip.
  const streamUnsupported = useRef(new Set<string>());

  useEffect(() => {
    const handles = inflight.current;
    return () => {
      for (const h of handles.values()) h.cancel();
      handles.clear();
    };
  }, []);

  const submit = useCallback(
    (request: TurnRequest) => {
      const id = newId();
      dispatch({ type: "start", id, request, at: Date.now() });
      let handle: RequestHandle<QueryResponse>;
      if (request.mode === "rag") {
        const payload: QueryRequest = {
          question: request.question,
          ...(request.patientId ? { patient_id: request.patientId } : {}),
          ...(request.structured ? { structured: true } : {}),
          session_id: state.sessionId.slice(0, 64),
        };
        handle =
          stream && !streamUnsupported.current.has(apiBase)
            ? runRagQueryStreaming(
                apiBase,
                payload,
                (step) => dispatch({ type: "progress", id, step }),
                () => streamUnsupported.current.add(apiBase),
              )
            : runRagQuery(apiBase, payload);
      } else {
        handle = runMcpTool(apiBase, request.tool, request.args ?? {});
      }
      inflight.current.set(id, handle);
      handle.promise
        .then((response) => dispatch({ type: "succeed", id, response, at: Date.now() }))
        .catch((err: unknown) => {
          const kind = err instanceof ApiError ? err.kind : "network";
          dispatch({
            type: "fail",
            id,
            status: kind === "cancelled" ? "cancelled" : kind === "timeout" ? "timeout" : "error",
            error: err instanceof Error ? err.message : "Request failed.",
            at: Date.now(),
          });
        })
        .finally(() => inflight.current.delete(id));
    },
    [apiBase, state.sessionId, stream],
  );

  const cancelAll = useCallback(() => {
    for (const h of inflight.current.values()) h.cancel();
  }, []);

  const reset = useCallback(() => {
    cancelAll();
    dispatch({ type: "reset", sessionId: newId() });
  }, [cancelAll]);

  const remove = useCallback((id: string) => {
    inflight.current.get(id)?.cancel();
    dispatch({ type: "remove", id });
  }, []);

  return { state, busy: isBusy(state), submit, cancelAll, reset, remove };
}
