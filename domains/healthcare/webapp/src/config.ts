// The only module that reads import.meta.env. Everything else imports `config`.

function readNumber(raw: string | undefined, fallback: number): number {
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

export const config = {
  defaultApiBaseUrl: (import.meta.env.VITE_API_BASE_URL as string | undefined) || "http://localhost:8000",
  callerId: (import.meta.env.VITE_CALLER_ID as string | undefined) || "",
  callerRole: (import.meta.env.VITE_CALLER_ROLE as string | undefined) || "",
  requestTimeoutMs: readNumber(import.meta.env.VITE_REQUEST_TIMEOUT_MS as string | undefined, 120_000),
  maxQuestionChars: 1000,
} as const;

export function normalizeBaseUrl(value: string): string {
  return value.trim().replace(/\/+$/, "");
}
