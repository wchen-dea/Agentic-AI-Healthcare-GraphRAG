 // Wire contract mirroring the healthcare agent service `/query` contract.
// Keep in sync with the backend response envelope.

export type ApiMode = "rag";

export interface QueryRequest {
  question: string;
  patient_id?: string;
  structured?: boolean;
  session_id?: string;
  top_k?: number;
}

export interface VectorEvidence {
  score: number | null;
  event_id: string | null;
  patient_id: string | null;
  event_type: string | null;
  text?: string;
  text_redacted?: boolean;
}

export type GraphEntity = Record<string, unknown> & {
  patient_id?: string;
  entity_id?: string;
};

export interface RetrievalPlan {
  name?: string;
  top_k?: number;
  reason?: string;
}

export interface Guardrails {
  evidence_text_redacted?: boolean;
  evidence_access_level?: string;
  graph_access_level?: string;
  response_truncated?: boolean;
  input_blocked?: boolean;
  output_blocked?: boolean;
  category?: string;
  [key: string]: unknown;
}

export interface ModelRouting {
  model?: string;
  tier?: string;
  downgraded?: boolean;
  [key: string]: unknown;
}

export interface ReactAction {
  iteration?: number;
  action?: string;
  plan_name?: string;
  top_k?: number;
  new_event_ids?: number;
  new_patient_ids?: number;
  confidence_after?: number;
}

export interface ReactTrace {
  iterations?: number;
  confidence?: number;
  final_reason?: string;
  actions: ReactAction[];
}

export type AgentTraceStep = Record<string, unknown> & {
  agent?: string;
  action?: string;
};

export interface LangGraphTrace {
  enabled?: boolean;
  iterations?: number;
  confidence?: number;
  final_reason?: string;
  agent_trace: AgentTraceStep[];
}

/** One `event: step` from `POST /query/stream`: an evidence-free progress update for a graph node. */
export interface AgentProgressStep {
  node: string;
  messages: AgentTraceStep[];
}

export interface AgentCard {
  name: string;
  description: string;
  capabilities: string[];
  accepted_inputs: string[];
}

export type Severity = "high" | "moderate" | "low" | "unknown";

export interface RiskFinding {
  category: string;
  severity: Severity;
  description: string;
  evidence_source: string;
}

export interface MedicationInteraction {
  drug_a: string;
  drug_b: string;
  mechanism: string;
  severity: Severity;
}

export interface LabSignal {
  observation: string;
  value: string;
  indicated_condition: string;
  reason: string;
}

export interface StructuredClinicalResponse {
  summary: string;
  key_findings: string[];
  risks: RiskFinding[];
  interactions: MedicationInteraction[];
  lab_signals: LabSignal[];
  confidence: number | null;
  safety_caveat: string;
}

export interface QueryResponse {
  answer: string;
  status?: string;
  thread_id?: string;
  human_review?: { reason?: string; decision?: string; note?: string; [key: string]: unknown };
  question?: string;
  request_type?: string;
  retrieval_plan?: RetrievalPlan;
  patients: string[];
  vector_context: VectorEvidence[];
  graph_context: GraphEntity[];
  retrieved_at?: string;
  trace_id?: string;
  guardrails?: Guardrails;
  model_routing?: ModelRouting;
  react?: ReactTrace;
  structured_response?: StructuredClinicalResponse;
  langgraph?: LangGraphTrace;
  /** Additional response fields not explicitly modeled above. */
  extra: Record<string, unknown>;
}

export interface HealthStatus {
  api: "ok" | "error";
  checkedAt: string;
}
