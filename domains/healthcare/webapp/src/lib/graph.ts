// Pure transformation of `graph_context` into a node/edge model for the knowledge-graph view.
import { isRecord, toSeverity } from "../api/guards";
import type { GraphEntity, Severity } from "../api/types";

export type NodeKind = "patient" | "condition" | "medication" | "observation" | "symptom" | "adverse_event";

export const NODE_KINDS: NodeKind[] = ["patient", "condition", "medication", "observation", "symptom", "adverse_event"];

export type EdgeKind =
  | "has_condition"
  | "takes"
  | "has_observation"
  | "has_symptom"
  | "interaction"
  | "contraindication"
  | "lab_signal"
  | "adverse_event";

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string;
  details: Record<string, unknown>;
  flagged: boolean;
  x: number;
  y: number;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label?: string;
  severity?: Severity;
}

export interface GraphModel {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

function text(value: unknown): string {
  return typeof value === "string" ? value.trim() : typeof value === "number" ? String(value) : "";
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

/** Items may arrive as strings (sanitized) or objects; return a display name for either. */
function nameOf(item: unknown, ...keys: string[]): string {
  if (typeof item === "string") return item.trim();
  if (!isRecord(item)) return "";
  for (const k of keys) {
    const v = text(item[k]);
    if (v) return v;
  }
  return "";
}

const slug = (s: string) => s.toLowerCase().replace(/\s+/g, " ").trim();

class Builder {
  readonly nodes = new Map<string, GraphNode>();
  readonly edges = new Map<string, GraphEdge>();

  node(kind: NodeKind, label: string, details: Record<string, unknown> = {}, flagged = false): string {
    const id = kind === "patient" ? `patient:${label}` : `${kind}:${slug(label)}`;
    const existing = this.nodes.get(id);
    if (existing) {
      existing.flagged ||= flagged;
      Object.assign(existing.details, details);
      return id;
    }
    this.nodes.set(id, { id, kind, label, details: { ...details }, flagged, x: 0, y: 0 });
    return id;
  }

  edge(source: string, target: string, kind: EdgeKind, label?: string, severity?: Severity): void {
    if (source === target) return;
    const id = `${kind}:${source}->${target}`;
    if (this.edges.has(id)) return;
    const edge: GraphEdge = { id, source, target, kind };
    if (label) edge.label = label;
    if (severity) edge.severity = severity;
    this.edges.set(id, edge);
  }
}

function addPatient(b: Builder, entity: GraphEntity): void {
  const patientId = text(entity.patient_id) || text(entity.entity_id);
  if (!patientId) return;
  const pid = b.node("patient", patientId, {
    age: entity.age,
    sex: entity.sex,
    risk_tier: entity.risk_tier,
  });

  for (const c of list(entity.conditions)) {
    const name = nameOf(c, "name", "condition");
    if (name) b.edge(pid, b.node("condition", name, isRecord(c) ? c : {}), "has_condition");
  }
  for (const code of list(entity.icd10_codes)) {
    const name = nameOf(code, "condition");
    if (name && isRecord(code)) b.node("condition", name, { icd10: code.icd10 });
  }
  for (const m of list(entity.medications)) {
    const name = nameOf(m, "medication", "name");
    if (name) b.edge(pid, b.node("medication", name, isRecord(m) ? m : {}), "takes");
  }
  for (const o of list(entity.observations)) {
    const name = nameOf(o, "name", "observation");
    if (!name) continue;
    const abnormal = isRecord(o) && (o.abnormal === true || o.abnormal === "true");
    b.edge(pid, b.node("observation", name, isRecord(o) ? o : {}, abnormal), "has_observation");
  }
  for (const s of list(entity.symptoms)) {
    const name = nameOf(s, "name", "symptom");
    if (name) b.edge(pid, b.node("symptom", name), "has_symptom");
  }
  for (const i of list(entity.interactions)) {
    if (!isRecord(i)) continue;
    const a = text(i.from);
    const c = text(i.to);
    if (!a || !c) continue;
    const severity = toSeverity(i.severity);
    b.edge(
      b.node("medication", a, {}, severity === "high"),
      b.node("medication", c, {}, severity === "high"),
      "interaction",
      text(i.risk) || "interaction",
      severity,
    );
  }
  for (const ci of list(entity.contraindications)) {
    if (!isRecord(ci)) continue;
    const med = text(ci.medication);
    const cond = text(ci.condition);
    if (!med || !cond) continue;
    b.edge(
      b.node("medication", med, {}, true),
      b.node("condition", cond),
      "contraindication",
      text(ci.reason) || "contraindicated",
      toSeverity(ci.severity),
    );
  }
  for (const ls of list(entity.lab_signals)) {
    if (!isRecord(ls)) continue;
    const obs = text(ls.observation);
    const cond = text(ls.indicated_condition);
    if (!obs || !cond) continue;
    b.edge(
      b.node("observation", obs, { value: ls.value, unit: ls.unit }, true),
      b.node("condition", cond),
      "lab_signal",
      text(ls.reason) || "indicates",
    );
  }
  for (const ae of list(entity.adverse_events)) {
    if (!isRecord(ae)) continue;
    const symptom = nameOf(ae, "meddra_term", "symptom");
    if (!symptom) continue;
    const aeId = b.node("adverse_event", symptom, ae, toSeverity(ae.severity) === "high");
    b.edge(pid, aeId, "adverse_event");
    const med = text(ae.medication);
    if (med) b.edge(b.node("medication", med), aeId, "adverse_event", "caused", toSeverity(ae.severity));
  }
}

const RING_ORDER: NodeKind[] = ["condition", "medication", "observation", "symptom", "adverse_event"];

/** Deterministic layout: patients in the centre, other kinds on sectors of a surrounding ring. */
function layout(nodes: GraphNode[], width: number, height: number): void {
  const cx = width / 2;
  const cy = height / 2;
  const patients = nodes.filter((n) => n.kind === "patient");
  patients.forEach((p, i) => {
    const angle = (2 * Math.PI * i) / Math.max(1, patients.length);
    const r = patients.length > 1 ? Math.min(width, height) * 0.12 : 0;
    p.x = cx + r * Math.cos(angle);
    p.y = cy + r * Math.sin(angle);
  });

  const others = RING_ORDER.flatMap((kind) => nodes.filter((n) => n.kind === kind));
  const radiusX = width * 0.4;
  const radiusY = height * 0.4;
  others.forEach((n, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / Math.max(1, others.length);
    // Alternate radii slightly so dense rings keep labels readable.
    const jitter = others.length > 16 && i % 2 === 1 ? 0.8 : 1;
    n.x = cx + radiusX * jitter * Math.cos(angle);
    n.y = cy + radiusY * jitter * Math.sin(angle);
  });
}

export function buildGraph(context: GraphEntity[], width = 800, height = 560): GraphModel {
  const b = new Builder();
  for (const entity of context) addPatient(b, entity);
  const nodes = [...b.nodes.values()];
  layout(nodes, width, height);
  return { nodes, edges: [...b.edges.values()] };
}

export function countByKind(model: GraphModel): Record<NodeKind, number> {
  const counts = Object.fromEntries(NODE_KINDS.map((k) => [k, 0])) as Record<NodeKind, number>;
  for (const n of model.nodes) counts[n.kind] += 1;
  return counts;
}
