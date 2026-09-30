import { useMemo, useState } from "react";
import type { VectorEvidence } from "../api/types";
import { formatScore } from "../lib/format";
import { Empty } from "./common";

type SortKey = "score" | "event_type" | "patient_id";

export function EvidenceView({ evidence }: { evidence: VectorEvidence[] }) {
  const [filter, setFilter] = useState("");
  const [type, setType] = useState("all");
  const [sort, setSort] = useState<SortKey>("score");

  const types = useMemo(
    () => [...new Set(evidence.map((e) => e.event_type).filter((t): t is string => Boolean(t)))].sort(),
    [evidence],
  );

  const rows = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    return evidence
      .filter((e) => type === "all" || e.event_type === type)
      .filter((e) =>
        !needle
          ? true
          : [e.event_id, e.patient_id, e.event_type, e.text].some((v) => v?.toLowerCase().includes(needle)),
      )
      .sort((a, b) =>
        sort === "score" ? (b.score ?? -Infinity) - (a.score ?? -Infinity) : (a[sort] ?? "").localeCompare(b[sort] ?? ""),
      );
  }, [evidence, filter, type, sort]);

  if (!evidence.length) return <Empty>No vector evidence was returned.</Empty>;
  const maxScore = Math.max(...evidence.map((e) => e.score ?? 0), 0.0001);

  return (
    <div className="evidence">
      <div className="toolbar">
        <input
          type="search"
          placeholder="Filter evidence…"
          aria-label="Filter evidence"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <select aria-label="Event type" value={type} onChange={(e) => setType(e.target.value)}>
          <option value="all">All types</option>
          {types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <select aria-label="Sort by" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
          <option value="score">Sort: score</option>
          <option value="event_type">Sort: type</option>
          <option value="patient_id">Sort: patient</option>
        </select>
        <span className="muted">
          {rows.length} / {evidence.length}
        </span>
      </div>
      <ul className="evidence-list">
        {rows.map((e, i) => (
          <li key={`${e.event_id ?? "evt"}-${i}`} className="card">
            <div className="card-head">
              <span className="badge">{e.event_type ?? "event"}</span>
              <code>{e.event_id ?? "—"}</code>
              <span className="muted">{e.patient_id ?? ""}</span>
              <span className="score" title="Similarity score">
                {formatScore(e.score)}
              </span>
            </div>
            <div className="score-bar">
              <div style={{ width: `${Math.max(0, ((e.score ?? 0) / maxScore) * 100)}%` }} />
            </div>
            {e.text_redacted ? (
              <p className="muted">Evidence text redacted for this access level.</p>
            ) : e.text ? (
              <p className="evidence-text">{e.text}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
