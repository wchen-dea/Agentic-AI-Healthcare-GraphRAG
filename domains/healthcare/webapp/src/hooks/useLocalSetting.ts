import { useEffect, useState } from "react";

// Only non-sensitive UI preferences are persisted. Never store questions, answers or tokens.
export type SettingKey = "hc.apiBase" | "hc.mode" | "hc.theme";

function read(key: SettingKey): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function useLocalSetting<T extends string>(
  key: SettingKey,
  fallback: T,
  isValid: (value: string) => value is T,
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    const stored = read(key);
    return stored !== null && isValid(stored) ? stored : fallback;
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Storage may be unavailable (private mode); preferences then last for the session only.
    }
  }, [key, value]);

  return [value, setValue];
}
