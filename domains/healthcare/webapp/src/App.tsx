import { useEffect, useRef, useState } from "react";
import { config, normalizeBaseUrl } from "./config";
import { QueryPanel } from "./components/QueryPanel";
import { PatientMemoryPanel } from "./components/PatientMemoryPanel";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { TurnCard } from "./components/TurnCard";
import { useAgents } from "./hooks/useAgents";
import { useConversation } from "./hooks/useConversation";
import { useHealth } from "./hooks/useHealth";
import { useLocalSetting } from "./hooks/useLocalSetting";

type Theme = "light" | "dark";

const isTheme = (v: string): v is Theme => v === "light" || v === "dark";
const isOnOff = (v: string): v is "on" | "off" => v === "on" || v === "off";
const isUrl = (v: string): v is string => /^(https?:\/\/|\/)/.test(v.trim());

function preferredTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function App() {
  const [apiBase, setApiBase] = useLocalSetting("hc.apiBase", config.defaultApiBaseUrl, isUrl);
  const [theme, setTheme] = useLocalSetting<Theme>("hc.theme", preferredTheme(), isTheme);
  const [streaming, setStreaming] = useLocalSetting<"on" | "off">("hc.stream", "on", isOnOff);
  const [apiDraft, setApiDraft] = useState(apiBase);
  const { health, checking, refresh } = useHealth(apiBase);
  const { agents } = useAgents(apiBase);
  const { state, busy, submit, cancelAll, reset, remove } = useConversation(apiBase, { stream: streaming === "on" });
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const turnCount = state.turns.length;
  const latestTurn = state.turns[turnCount - 1];
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [turnCount]);

  const commitApiBase = () => {
    const next = normalizeBaseUrl(apiDraft);
    if (isUrl(next)) setApiBase(next);
    else setApiDraft(apiBase);
  };

  const apiState = health === null ? "unknown" : health.api;

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="logo" aria-hidden="true">
            ✚
          </span>
          <div>
            <h1>Healthcare GraphRAG</h1>
            <p className="muted">Provider clinical decision support · vector + knowledge-graph evidence</p>
          </div>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="health"
            onClick={refresh}
            title={health ? `Checked ${new Date(health.checkedAt).toLocaleTimeString()}` : "Checking…"}
          >
            <span className={`dot status-${checking ? "checking" : apiState}`} /> API
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
          >
            {theme === "dark" ? "☀ Light" : "☾ Dark"}
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <section className="panel">
            <ErrorBoundary label="Query form">
              <QueryPanel busy={busy} onSubmit={submit} onCancel={cancelAll} />
            </ErrorBoundary>
          </section>

          <section className="panel">
            <ErrorBoundary label="Governed patient memory">
              <PatientMemoryPanel
                apiBase={apiBase}
                patientId={latestTurn?.request.patientId}
                answer={latestTurn?.response?.answer}
              />
            </ErrorBoundary>
          </section>

          <section className="panel settings">
            <label className="field" htmlFor="api-base">
              <span>API base URL</span>
              <input
                id="api-base"
                value={apiDraft}
                onChange={(e) => setApiDraft(e.target.value)}
                onBlur={commitApiBase}
                onKeyDown={(e) => e.key === "Enter" && commitApiBase()}
              />
            </label>
            <label className="check">
              <input
                type="checkbox"
                checked={streaming === "on"}
                onChange={(e) => setStreaming(e.target.checked ? "on" : "off")}
              />
              Stream agent steps (LangGraph orchestrator)
            </label>
            <div className="session-row">
              <span className="muted" title={state.sessionId}>
                Session <code>{state.sessionId.slice(0, 8)}</code> · {turnCount} turn(s)
              </span>
              <button type="button" className="btn btn-ghost btn-sm" onClick={reset} disabled={!turnCount && !busy}>
                New session
              </button>
            </div>
            <p className="muted small">
              Decision support only — clinical review required. Questions and answers are kept in memory for this tab and
              never persisted.
            </p>
            {agents.length > 0 && (
              <details className="examples">
                <summary>Registered agents ({agents.length})</summary>
                <ul>
                  {agents.map((a) => (
                    <li key={a.name}>
                      <strong>{a.name}</strong> — {a.description}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </section>
        </aside>

        <main className="thread" aria-live="polite">
          {turnCount === 0 ? (
            <div className="welcome">
              <h2>Ask a clinical question</h2>
              <p className="muted">
                Combine semantic evidence from patient events with the clinical knowledge graph — conditions, medications,
                labs, interactions and contraindications. Pick an example scenario to get started.
              </p>
              <ul className="feature-list">
                <li>Structured risk, interaction and lab-signal summaries with confidence</li>
                <li>Interactive knowledge-graph explorer</li>
                <li>Evidence ranking, filtering and redaction awareness</li>
                <li>Retrieval plan, guardrail and ReAct trace inspection</li>
                <li>Markdown / JSON export for review workflows</li>
              </ul>
            </div>
          ) : (
            state.turns.map((turn, i) => (
              <div key={turn.id} ref={i === turnCount - 1 ? endRef : undefined}>
                <ErrorBoundary label="This result">
                  <TurnCard turn={turn} onRemove={() => remove(turn.id)} onRetry={() => submit(turn.request)} />
                </ErrorBoundary>
              </div>
            ))
          )}
        </main>
      </div>
    </div>
  );
}
