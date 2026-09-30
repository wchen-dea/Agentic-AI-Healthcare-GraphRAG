import { useCallback, useEffect, useReducer, useRef } from "react";
import { ApiError, runMcpTool, runRagQuery, type RequestHandle } from "../api/client";
import type { QueryResponse } from "../api/types";
import { conversationReducer, initialConversation, isBusy, type TurnRequest } from "../lib/conversation";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function useConversation(apiBase: string) {
  const [state, dispatch] = useReducer(conversationReducer, undefined, () => initialConversation(newId()));
  const inflight = useRef(new Map<string, RequestHandle<QueryResponse>>());

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
      const handle =
        request.mode === "rag"
          ? runRagQuery(apiBase, {
              question: request.question,
              ...(request.patientId ? { patient_id: request.patientId } : {}),
              ...(request.structured ? { structured: true } : {}),
              session_id: state.sessionId.slice(0, 64),
            })
          : runMcpTool(apiBase, request.tool, request.args ?? {});
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
    [apiBase, state.sessionId],
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
