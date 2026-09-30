// Narrow untrusted wire data (`unknown`) into typed view models.
import type {
  GraphEntity,
  Guardrails,
  LabSignal,
  MedicationInteraction,
  ModelRouting,
  QueryResponse,
  ReactAction,
  ReactTrace,
  RetrievalPlan,
  RiskFinding,
  Severity,
  StructuredClinicalResponse,
  VectorEvidence,
} from "./types";

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function num(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function bool(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function records(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

export function toSeverity(value: unknown): Severity {
  const s = typeof value === "string" ? value.toLowerCase() : "";
  return s === "high" || s === "moderate" || s === "low" ? s : "unknown";
}

function parseVector(item: Record<string, unknown>): VectorEvidence {
  const out: VectorEvidence = {
    score: num(item.score) ?? null,
    event_id: str(item.event_id) ?? null,
    patient_id: str(item.patient_id) ?? null,
    event_type: str(item.event_type) ?? null,
  };
  const text = str(item.text);
  if (text !== undefined) out.text = text;
  if (item.text_redacted === true) out.text_redacted = true;
  return out;
}

function parsePlan(value: unknown): RetrievalPlan | undefined {
  if (!isRecord(value)) return undefined;
  return { name: str(value.name), top_k: num(value.top_k), reason: str(value.reason) };
}

function parseReact(value: unknown): ReactTrace | undefined {
  if (!isRecord(value)) return undefined;
  const actions: ReactAction[] = records(value.actions).map((a) => ({
    iteration: num(a.iteration),
    action: str(a.action),
    plan_name: str(a.plan_name),
    top_k: num(a.top_k),
    new_event_ids: num(a.new_event_ids),
    new_patient_ids: num(a.new_patient_ids),
    confidence_after: num(a.confidence_after),
  }));
  return {
    iterations: num(value.iterations),
    confidence: num(value.confidence),
    final_reason: str(value.final_reason),
    actions,
  };
}

export function parseStructured(value: unknown): StructuredClinicalResponse | undefined {
  if (!isRecord(value)) return undefined;
  const risks: RiskFinding[] = records(value.risks).map((r) => ({
    category: str(r.category) ?? "risk",
    severity: toSeverity(r.severity),
    description: str(r.description) ?? "",
    evidence_source: str(r.evidence_source) ?? "",
  }));
  const interactions: MedicationInteraction[] = records(value.interactions).map((i) => ({
    drug_a: str(i.drug_a) ?? "?",
    drug_b: str(i.drug_b) ?? "?",
    mechanism: str(i.mechanism) ?? "",
    severity: toSeverity(i.severity),
  }));
  const labSignals: LabSignal[] = records(value.lab_signals).map((l) => ({
    observation: str(l.observation) ?? "Observation",
    value: str(l.value) ?? "",
    indicated_condition: str(l.indicated_condition) ?? "",
    reason: str(l.reason) ?? "",
  }));
  return {
    summary: str(value.summary) ?? "",
    key_findings: Array.isArray(value.key_findings)
      ? value.key_findings.filter((f): f is string => typeof f === "string")
      : [],
    risks,
    interactions,
    lab_signals: labSignals,
    confidence: num(value.confidence) ?? null,
    safety_caveat: str(value.safety_caveat) ?? "",
  };
}

const KNOWN_KEYS = new Set([
  "answer",
  "question",
  "request_type",
  "retrieval_plan",
  "patients",
  "vector_context",
  "graph_context",
  "retrieved_at",
  "trace_id",
  "guardrails",
  "model_routing",
  "react",
  "structured_response",
]);

/** Converts any `/query` or MCP tool payload into the unified view model. */
export function parseQueryResponse(value: unknown): QueryResponse {
  const data = isRecord(value) ? value : {};
  const extra: Record<string, unknown> = {};
  for (const [key, v] of Object.entries(data)) {
    if (!KNOWN_KEYS.has(key)) extra[key] = v;
  }
  const answer = str(data.answer) ?? str(data.summary) ?? "";
  return {
    answer,
    question: str(data.question),
    request_type: str(data.request_type),
    retrieval_plan: parsePlan(data.retrieval_plan),
    patients: Array.isArray(data.patients) ? data.patients.filter((p): p is string => typeof p === "string") : [],
    vector_context: records(data.vector_context).map(parseVector),
    graph_context: records(data.graph_context) as GraphEntity[],
    retrieved_at: str(data.retrieved_at),
    trace_id: str(data.trace_id),
    guardrails: isRecord(data.guardrails) ? (data.guardrails as Guardrails) : undefined,
    model_routing: isRecord(data.model_routing)
      ? ({
          ...data.model_routing,
          model: str(data.model_routing.model),
          tier: str(data.model_routing.tier),
          downgraded: bool(data.model_routing.downgraded),
        } as ModelRouting)
      : undefined,
    react: parseReact(data.react),
    structured_response: parseStructured(data.structured_response),
    extra,
  };
}

/** Best-effort extraction of a FastAPI error detail. */
export function errorDetail(value: unknown): string | undefined {
  if (!isRecord(value)) return undefined;
  const detail = value.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail.filter(isRecord).map((d) => str(d.msg)).filter((m): m is string => Boolean(m));
    return msgs.length ? msgs.join("; ") : undefined;
  }
  return undefined;
}
