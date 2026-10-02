import { useMemo, useState } from "react";
import type { GraphEntity } from "../api/types";
import { buildGraph, countByKind, NODE_KINDS, type GraphNode, type NodeKind } from "../lib/graph";
import { displayValue, humanizeKey } from "../lib/format";
import { Empty, KeyValueGrid } from "./common";

const WIDTH = 820;
const HEIGHT = 560;

const KIND_LABEL: Record<NodeKind, string> = {
  patient: "Patient",
  condition: "Condition",
  medication: "Medication",
  observation: "Lab / observation",
  symptom: "Symptom",
  adverse_event: "Adverse event",
};

function truncate(s: string, n = 18): string {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

function NodeDetails({ node }: { node: GraphNode }) {
  const entries = Object.entries(node.details).filter(([, v]) => v !== undefined && v !== null && v !== "");
  return (
    <aside className="node-details" aria-live="polite">
      <h4>
        <span className={`dot kind-${node.kind}`} /> {node.label}
      </h4>
      <p className="muted">{KIND_LABEL[node.kind]}{node.flagged ? " · flagged" : ""}</p>
      {entries.length ? (
        <KeyValueGrid entries={entries.map(([k, v]) => [humanizeKey(k), displayValue(v)])} />
      ) : (
        <p className="muted">No additional attributes.</p>
      )}
    </aside>
  );
}

function FactsList({ entity }: { entity: GraphEntity }) {
  const entries = Object.entries(entity).filter(([k, v]) => k !== "patient_id" && v !== null && v !== undefined);
  return (
    <details className="facts">
      <summary>
        Raw graph facts — {String(entity.patient_id ?? entity.entity_id ?? "entity")}
      </summary>
      {entries.map(([key, value]) => (
        <div key={key} className="fact-group">
          <h5>{humanizeKey(key)}</h5>
          {Array.isArray(value) ? (
            value.length ? (
              <ul>
                {value.map((item, i) => (
                  <li key={i}>{displayValue(item)}</li>
                ))}
              </ul>
            ) : (
              <p className="muted">None</p>
            )
          ) : (
            <p>{displayValue(value)}</p>
          )}
        </div>
      ))}
    </details>
  );
}

export function GraphView({ context }: { context: GraphEntity[] }) {
  const model = useMemo(() => buildGraph(context, WIDTH, HEIGHT), [context]);
  const counts = useMemo(() => countByKind(model), [model]);
  const [hidden, setHidden] = useState<Set<NodeKind>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  if (!context.length) return <Empty>No knowledge-graph context was returned.</Empty>;

  const visible = new Map(model.nodes.filter((n) => !hidden.has(n.kind)).map((n) => [n.id, n]));
  const edges = model.edges.filter((e) => visible.has(e.source) && visible.has(e.target));
  const focus = hovered ?? selected;
  const neighbours = new Set<string>();
  if (focus) {
    neighbours.add(focus);
    for (const e of edges) {
      if (e.source === focus) neighbours.add(e.target);
      if (e.target === focus) neighbours.add(e.source);
    }
  }
  const selectedNode = selected ? model.nodes.find((n) => n.id === selected) : undefined;

  const toggle = (kind: NodeKind) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });

  return (
    <div className="graph-view">
      <div className="legend" role="group" aria-label="Toggle node types">
        {NODE_KINDS.filter((k) => counts[k] > 0).map((kind) => (
          <button
            key={kind}
            type="button"
            className={`legend-item${hidden.has(kind) ? " off" : ""}`}
            aria-pressed={!hidden.has(kind)}
            onClick={() => toggle(kind)}
          >
            <span className={`dot kind-${kind}`} /> {KIND_LABEL[kind]} ({counts[kind]})
          </button>
        ))}
        <span className="legend-item static">
          <span className="line line-interaction" /> Interaction
        </span>
        <span className="legend-item static">
          <span className="line line-contraindication" /> Contraindication
        </span>
        <span className="legend-item static">
          <span className="line line-lab_signal" /> Lab signal
        </span>
      </div>

      <div className="graph-layout">
        <svg
          className="graph-svg"
          viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
          role="img"
          aria-label={`Knowledge graph with ${visible.size} nodes and ${edges.length} edges`}
          onClick={() => setSelected(null)}
        >
          <defs>
            <marker id="arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" className="arrow-head" />
            </marker>
          </defs>
          {edges.map((e) => {
            const s = visible.get(e.source);
            const t = visible.get(e.target);
            if (!s || !t) return null;
            const dim = focus !== null && !(neighbours.has(e.source) && neighbours.has(e.target));
            const semantic = e.kind === "interaction" || e.kind === "contraindication" || e.kind === "lab_signal";
            return (
              <g key={e.id} className={`edge edge-${e.kind}${dim ? " dim" : ""}`}>
                <line
                  x1={s.x}
                  y1={s.y}
                  x2={t.x}
                  y2={t.y}
                  markerEnd={e.kind === "interaction" ? undefined : "url(#arrow)"}
                />
                {semantic && e.label && !dim && focus !== null && (
                  <text x={(s.x + t.x) / 2} y={(s.y + t.y) / 2} className="edge-label">
                    {truncate(e.label, 28)}
                  </text>
                )}
                <title>{`${e.kind.replace(/_/g, " ")}${e.label ? `: ${e.label}` : ""}${e.severity ? ` (${e.severity})` : ""}`}</title>
              </g>
            );
          })}
          {[...visible.values()].map((n) => {
            const dim = focus !== null && !neighbours.has(n.id);
            const r = n.kind === "patient" ? 22 : 12;
            return (
              <g
                key={n.id}
                className={`node kind-${n.kind}${n.flagged ? " flagged" : ""}${dim ? " dim" : ""}${selected === n.id ? " selected" : ""}`}
                transform={`translate(${n.x},${n.y})`}
                tabIndex={0}
                role="button"
                aria-label={`${KIND_LABEL[n.kind]}: ${n.label}`}
                onMouseEnter={() => setHovered(n.id)}
                onMouseLeave={() => setHovered(null)}
                onFocus={() => setHovered(n.id)}
                onBlur={() => setHovered(null)}
                onClick={(ev) => {
                  ev.stopPropagation();
                  setSelected(n.id);
                }}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    setSelected(n.id);
                  }
                }}
              >
                <circle r={r} />
                <text y={r + 13} textAnchor="middle">
                  {truncate(n.label)}
                </text>
                <title>{n.label}</title>
              </g>
            );
          })}
        </svg>
        {selectedNode ? (
          <NodeDetails node={selectedNode} />
        ) : (
          <aside className="node-details muted">Select a node to inspect its attributes. Hover to highlight neighbours.</aside>
        )}
      </div>

      {context.map((entity, i) => (
        <FactsList key={String(entity.patient_id ?? i)} entity={entity} />
      ))}
    </div>
  );
}
