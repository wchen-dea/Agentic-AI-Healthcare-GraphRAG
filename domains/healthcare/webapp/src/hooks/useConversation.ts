import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, runRagQuery, runRagQueryStreaming, type RequestHandle } from "../api/client";
import type { QueryRequest, QueryResponse } from "../api/types";
import { conversationReducer, initialConversation, isBusy, type TurnRequest } from "../lib/conversation";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export interface ConversationOptions {
  stream: boolean;
}

export function useConversation(apiBase: string, { stream }: ConversationOptions = { stream: false }) {
  const [state, dispatch] = useReducer(conversationReducer, undefined, () => initialConversation(newId()));
  const inflight = useRef(new Map<string, RequestHandle<QueryResponse>>());
  const streamUnsupported = useRef(new Set<string>());

  useEffect(() => {
    const handles = inflight.current;
    return () => {
      for (const handle of handles.values()) handle.cancel();
      handles.clear();
    };
  }, []);

  const submit = useCallback(
    (request: TurnRequest) => {
      const id = newId();
      dispatch({ type: "start", id, request, at: Date.now() });

      const payload: QueryRequest = {
        question: request.question,
        ...(request.patientId ? { patient_id: request.patientId } : {}),
        ...(request.structured ? { structured: true } : {}),
        ...(request.topK !== undefined ? { top_k: request.topK } : {}),
        session_id: state.sessionId.slice(0, 64),
      };

      const handle =
        stream && !streamUnsupported.current.has(apiBase)
          ? runRagQueryStreaming(
              apiBase,
              payload,
              (step) => dispatch({ type: "progress", id, step }),
              () => streamUnsupported.current.add(apiBase),
            )
          : runRagQuery(apiBase, payload);

      inflight.current.set(id, handle);
      handle.promise
        .then((response) => dispatch({ type: "succeed", id, response, at: Date.now() }))
        .catch((error: unknown) => {
          const kind = error instanceof ApiError ? error.kind : "network";
          dispatch({
            type: "fail",
            id,
            status: kind === "cancelled" ? "cancelled" : kind === "timeout" ? "timeout" : "error",
            error: error instanceof Error ? error.message : "Request failed.",
            at: Date.now(),
          });
        })
        .finally(() => inflight.current.delete(id));
    },
    [apiBase, state.sessionId, stream],
  );

  const cancelAll = useCallback(() => {
    for (const handle of inflight.current.values()) handle.cancel();
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