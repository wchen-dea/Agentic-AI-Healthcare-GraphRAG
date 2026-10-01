import { useEffect, useState } from "react";
import { getAgents } from "../api/client";
import type { AgentCard } from "../api/types";

/** Fetches the static LangGraph agent registry once per API base. */
export function useAgents(apiBase: string): { agents: AgentCard[] } {
  const [agents, setAgents] = useState<AgentCard[]>([]);

  useEffect(() => {
    let active = true;
    const handle = getAgents(apiBase);
    handle.promise
      .then((a) => active && setAgents(a))
      .catch(() => active && setAgents([]));
    return () => {
      active = false;
      handle.cancel();
    };
  }, [apiBase]);

  return { agents };
}
