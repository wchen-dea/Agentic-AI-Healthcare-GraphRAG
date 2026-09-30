import type { QueryResponse } from "../api/types";
import { displayValue, formatPercent, formatTime, humanizeKey } from "../lib/format";
import { CopyButton, KeyValueGrid } from "./common";

function flag(value: unknown): string {
  return value === true ? "yes" : value === false ? "no" : displayValue(value);
}

export function TraceView({ response }: { response: QueryResponse }) {
  const plan = response.retrieval_plan;
  const routing = response.model_routing;
  const react = response.react;
  const guardrails = response.guardrails;

  return (
    <div className="trace-view">
      <section>
        <h4>Request</h4>
        <KeyValueGrid
          entries={[
            ["Trace ID", response.trace_id ? (
              <span className="inline">
                <code>{response.trace_id}</code> <CopyButton text={response.trace_id} />
              </span>
            ) : "—"],
            ["Request type", response.request_type ?? "—"],
            ["Retrieved at", formatTime(response.retrieved_at)],
            ["Patients", response.patients.length ? response.patients.join(", ") : "—"],
          ]}
        />
      </section>

      {plan && (
        <section>
          <h4>Retrieval plan</h4>
          <KeyValueGrid
            entries={[
              ["Plan", plan.name ?? "—"],
              ["Top K", displayValue(plan.top_k)],
              ["Reason", plan.reason ?? "—"],
            ]}
          />
        </section>
      )}

      {routing && (
        <section>
          <h4>Model routing</h4>
          <KeyValueGrid entries={Object.entries(routing).map(([k, v]) => [humanizeKey(k), flag(v)])} />
        </section>
      )}

      {guardrails && (
        <section>
          <h4>Guardrails</h4>
          <KeyValueGrid entries={Object.entries(guardrails).map(([k, v]) => [humanizeKey(k), flag(v)])} />
        </section>
      )}

      {react && (
        <section>
          <h4>ReAct loop</h4>
          <p className="muted">
            {react.iterations ?? react.actions.length} iteration(s) · final confidence {formatPercent(react.confidence)}
            {react.final_reason ? ` · stopped: ${react.final_reason}` : ""}
          </p>
          <ol className="timeline">
            {react.actions.map((a, i) => (
              <li key={i}>
                <strong>
                  #{a.iteration ?? i + 1} {a.action ?? "step"}
                </strong>
                {a.plan_name && <span> · plan {a.plan_name}</span>}
                {a.top_k !== undefined && <span> · top_k {a.top_k}</span>}
                <div className="muted">
                  +{a.new_event_ids ?? 0} events, +{a.new_patient_ids ?? 0} patients · confidence{" "}
                  {formatPercent(a.confidence_after)}
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

export function RawView({ value }: { value: unknown }) {
  const json = JSON.stringify(value, null, 2);
  return (
    <div className="raw-view">
      <div className="answer-head">
        <h4>Raw JSON</h4>
        <CopyButton text={json} />
      </div>
      <pre className="code">{json}</pre>
    </div>
  );
}
