import type { QueryResponse, StructuredClinicalResponse } from "../api/types";
import { formatPercent } from "../lib/format";
import { CopyButton, SeverityBadge } from "./common";

function Blocked({ response }: { response: QueryResponse }) {
  const g = response.guardrails;
  if (!g?.input_blocked && !g?.output_blocked) return null;
  return (
    <div className="alert alert-warn" role="alert">
      <strong>{g.input_blocked ? "Input blocked by guardrails" : "Output blocked by guardrails"}</strong>
      {g.category ? <span> — category: {g.category}</span> : null}
    </div>
  );
}

function StructuredView({ s }: { s: StructuredClinicalResponse }) {
  const counts = { high: 0, moderate: 0, low: 0, unknown: 0 };
  for (const r of s.risks) counts[r.severity] += 1;
  for (const i of s.interactions) counts[i.severity] += 1;
  const confidence = s.confidence ?? 0;

  return (
    <div className="structured">
      <div className="stat-row">
        <div className="stat">
          <span className="stat-label">Confidence</span>
          <span className="stat-value">{formatPercent(s.confidence)}</span>
          <div className="meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(confidence * 100)}>
            <div className="meter-fill" style={{ width: `${Math.round(confidence * 100)}%` }} />
          </div>
        </div>
        {(["high", "moderate", "low"] as const).map((sev) => (
          <div key={sev} className={`stat stat-${sev}`}>
            <span className="stat-label">{sev} risk</span>
            <span className="stat-value">{counts[sev]}</span>
          </div>
        ))}
      </div>

      {s.key_findings.length > 0 && (
        <section>
          <h4>Key findings</h4>
          <ul className="findings">
            {s.key_findings.map((f, i) => (
              <li key={i}>{f}</li>
            ))}
          </ul>
        </section>
      )}

      {s.risks.length > 0 && (
        <section>
          <h4>Risks</h4>
          <ul className="card-list">
            {s.risks.map((r, i) => (
              <li key={i} className={`card sev-border-${r.severity}`}>
                <div className="card-head">
                  <SeverityBadge severity={r.severity} />
                  <strong>{r.category}</strong>
                </div>
                <p>{r.description}</p>
                {r.evidence_source && <small className="muted">Source: {r.evidence_source}</small>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {s.interactions.length > 0 && (
        <section>
          <h4>Medication interactions</h4>
          <ul className="card-list">
            {s.interactions.map((m, i) => (
              <li key={i} className={`card sev-border-${m.severity}`}>
                <div className="card-head">
                  <SeverityBadge severity={m.severity} />
                  <strong>
                    {m.drug_a} ↔ {m.drug_b}
                  </strong>
                </div>
                {m.mechanism && <p>{m.mechanism}</p>}
              </li>
            ))}
          </ul>
        </section>
      )}

      {s.lab_signals.length > 0 && (
        <section>
          <h4>Lab signals</h4>
          <table className="table">
            <thead>
              <tr>
                <th>Observation</th>
                <th>Value</th>
                <th>Indicates</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {s.lab_signals.map((l, i) => (
                <tr key={i}>
                  <td>{l.observation}</td>
                  <td>{l.value}</td>
                  <td>{l.indicated_condition}</td>
                  <td>{l.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {s.safety_caveat && <p className="caveat">{s.safety_caveat}</p>}
    </div>
  );
}

export function AnswerView({ response }: { response: QueryResponse }) {
  const s = response.structured_response;
  return (
    <div className="answer-view">
      <Blocked response={response} />
      <div className="answer-head">
        <h3>Answer</h3>
        <CopyButton text={response.answer} />
      </div>
      <div className="answer-text" aria-live="polite">
        {response.answer || <span className="muted">No answer text returned.</span>}
      </div>
      {s && <StructuredView s={s} />}
    </div>
  );
}
