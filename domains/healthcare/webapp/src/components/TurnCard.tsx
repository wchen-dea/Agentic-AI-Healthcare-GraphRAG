import { useState } from "react";
import type { AgentProgressStep } from "../api/types";
import type { Turn } from "../lib/conversation";
import { turnToJson, turnToMarkdown } from "../lib/export";
import { AnswerView } from "./AnswerView";
import { EvidenceView } from "./EvidenceView";
import { GraphView } from "./GraphView";
import { RawView, TraceView } from "./TraceView";
import { downloadText } from "./common";

type Tab = "answer" | "evidence" | "graph" | "trace" | "tool" | "raw";

const STATUS_LABEL: Record<Turn["status"], string> = {
  pending: "Running…",
  success: "Done",
  error: "Error",
  cancelled: "Cancelled",
  timeout: "Timed out",
};

function Elapsed({ turn }: { turn: Turn }) {
  if (!turn.finishedAt) return null;
  return <span className="muted">{((turn.finishedAt - turn.startedAt) / 1000).toFixed(1)}s</span>;
}

function stepSummary(step: AgentProgressStep): string {
  const msg = step.messages[step.messages.length - 1];
  if (!msg) return "";
  const details = Object.entries(msg)
    .filter(
      ([key, value]) =>
        key !== "agent" && key !== "action" && ["string", "number", "boolean"].includes(typeof value),
    )
    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${String(value)}`);
  return [msg.action, ...details].filter(Boolean).join(" · ");
}

function AgentSteps({ steps }: { steps: AgentProgressStep[] }) {
  return (
    <ol className="agent-steps" aria-label="Agent progress" aria-live="polite">
      {steps.map((step, i) => (
        <li key={`${step.node}-${i}`} className={i === steps.length - 1 ? "current" : undefined}>
          <code>{step.node}</code> <span className="muted">{stepSummary(step)}</span>
        </li>
      ))}
    </ol>
  );
}

export function TurnCard({ turn, onRemove, onRetry }: { turn: Turn; onRemove: () => void; onRetry: () => void }) {
  const [selectedTab, setTab] = useState<Tab | null>(null);
  const r = turn.response;
  const hasExtra = r !== undefined && Object.keys(r.extra).length > 0;
  // Tools without answer text (e.g. skills plans, exports) open on their payload instead of an empty answer.
  const defaultTab: Tab = r && !r.answer && !r.structured_response && hasExtra ? "tool" : "answer";
  const tab = selectedTab ?? defaultTab;
  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: "answer", label: "Answer", show: true },
    { id: "evidence", label: `Evidence (${r?.vector_context.length ?? 0})`, show: true },
    { id: "graph", label: `Knowledge graph (${r?.graph_context.length ?? 0})`, show: true },
    { id: "trace", label: "Trace", show: true },
    { id: "tool", label: "Tool output", show: hasExtra },
    { id: "raw", label: "Raw", show: true },
  ];
  const stamp = new Date(turn.startedAt).toISOString().replace(/[:.]/g, "-");

  return (
    <article className={`turn status-${turn.status}`} aria-busy={turn.status === "pending"}>
      <header className="turn-head">
        <div className="turn-title">
          <span className="badge">RAG</span>
          {turn.request.patientId && <span className="badge badge-outline">{turn.request.patientId}</span>}
          {turn.request.structured && <span className="badge badge-outline">structured</span>}
          <p className="turn-question">{turn.request.question || "(tool call)"}</p>
        </div>
        <div className="turn-actions">
          <span className={`status-pill status-${turn.status}`}>{STATUS_LABEL[turn.status]}</span>
          <Elapsed turn={turn} />
          {turn.status !== "pending" && (
            <>
              <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
                Re-run
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => downloadText(`graphrag-${stamp}.md`, turnToMarkdown(turn), "text/markdown")}
              >
                Export MD
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => downloadText(`graphrag-${stamp}.json`, turnToJson(turn), "application/json")}
              >
                Export JSON
              </button>
            </>
          )}
          <button type="button" className="btn btn-ghost btn-sm" onClick={onRemove} aria-label="Remove result">
            {turn.status === "pending" ? "Cancel" : "✕"}
          </button>
        </div>
      </header>

      {turn.status === "pending" && turn.steps && turn.steps.length > 0 && <AgentSteps steps={turn.steps} />}

      {turn.status === "pending" && (
        <div className="skeleton" aria-label="Loading">
          <div />
          <div />
          <div />
        </div>
      )}

      {turn.error && (
        <div className={`alert ${turn.status === "error" ? "alert-error" : "alert-warn"}`} role="alert">
          {turn.error}
        </div>
      )}

      {r && (
        <>
          <div className="tabs" role="tablist">
            {tabs
              .filter((t) => t.show)
              .map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="tab"
                  aria-selected={tab === t.id}
                  className={`tab${tab === t.id ? " active" : ""}`}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                </button>
              ))}
          </div>
          <div className="tab-panel" role="tabpanel">
            {tab === "answer" && <AnswerView response={r} />}
            {tab === "evidence" && <EvidenceView evidence={r.vector_context} />}
            {tab === "graph" && <GraphView context={r.graph_context} />}
            {tab === "trace" && <TraceView response={r} />}
            {tab === "tool" && <RawView value={r.extra} />}
            {tab === "raw" && <RawView value={r} />}
          </div>
        </>
      )}
    </article>
  );
}
