import { useCallback, useEffect, useState } from "react";
import { checkHealth } from "../api/client";
import type { HealthStatus } from "../api/types";

const POLL_MS = 30_000;

export function useHealth(apiBase: string): { health: HealthStatus | null; checking: boolean; refresh: () => void } {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [checking, setChecking] = useState(false);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let active = true;
    let handle = checkHealth(apiBase);
    const run = () => {
      setChecking(true);
      handle.promise
        .then((h) => active && setHealth(h))
        .catch(() => active && setHealth({ api: "error", checkedAt: new Date().toISOString() }))
        .finally(() => active && setChecking(false));
    };
    run();
    const timer = setInterval(() => {
      handle = checkHealth(apiBase);
      run();
    }, POLL_MS);
    return () => {
      active = false;
      clearInterval(timer);
      handle.cancel();
    };
  }, [apiBase, nonce]);

  const refresh = useCallback(() => setNonce((n) => n + 1), []);
  return { health, checking, refresh };
}
