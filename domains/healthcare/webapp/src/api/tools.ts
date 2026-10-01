// MCP tool catalog mirroring the MCP tools in domains/healthcare/agent-service/src/healthcare_agent/tools/mcp_server.py.
// Roles are fixed server-side per tool (config/tool_policies.json); shown here for transparency.

export type ToolFieldType = "text" | "textarea" | "number" | "boolean" | "select";

export interface ToolField {
  name: string;
  label: string;
  type: ToolFieldType;
  required?: boolean;
  default?: string | number | boolean;
  placeholder?: string;
  min?: number;
  max?: number;
  /** Allowed values for "select" fields; must mirror the server-side enum. */
  options?: string[];
}

export interface ToolSpec {
  name: string;
  title: string;
  description: string;
  role: "read_only" | "generation" | "export";
  fields: ToolField[];
}

const patientField: ToolField = {
  name: "patient_id",
  label: "Patient ID",
  type: "text",
  required: true,
  placeholder: "patient-0001",
};
const optionalPatient: ToolField = { ...patientField, required: false, default: "" };
const questionField: ToolField = {
  name: "question",
  label: "Question",
  type: "textarea",
  required: true,
};

export const MCP_TOOLS: ToolSpec[] = [
  {
    name: "graphrag_answer_generate",
    title: "GraphRAG answer",
    description: "Grounded answer over vector evidence and the clinical knowledge graph.",
    role: "generation",
    fields: [questionField, optionalPatient, {
        name: "response_style",
        label: "Response style",
        type: "select",
        default: "concise",
        // Mirrors GraphRagAnswerRequest.response_style in app.py.
        options: ["concise", "clinical", "audit"],
      }],
  },
  {
    name: "medication_risk_assess",
    title: "Medication risk assessment",
    description: "Interactions, contraindications and lab-confirmed medication risks for a patient.",
    role: "generation",
    fields: [patientField],
  },
  {
    name: "risk_summary_generate",
    title: "Risk summary",
    description: "Summarize recent clinical risk within a time window.",
    role: "generation",
    fields: [patientField, { name: "time_window_hours", label: "Window (hours)", type: "number", default: 72, min: 1, max: 720 }],
  },
  {
    name: "timeline_explain",
    title: "Timeline explanation",
    description: "Explain the patient's clinical event timeline.",
    role: "generation",
    fields: [patientField, { name: "time_window_hours", label: "Window (hours)", type: "number", default: 168, min: 1, max: 2160 }],
  },
  {
    name: "coding_gap_detect",
    title: "Coding gap detection",
    description: "Review ICD-10 coding and claims consistency gaps.",
    role: "generation",
    fields: [
      patientField,
      { ...questionField, required: false, default: "Review coding and claims consistency gaps for this patient." },
    ],
  },
  {
    name: "cohort_risk_summary",
    title: "Cohort risk summary",
    description: "Population-level risk summary across matching patients.",
    role: "generation",
    fields: [questionField, { name: "top_k", label: "Top K", type: "number", default: 5, min: 1, max: 20 }],
  },
  {
    name: "patient_context_get",
    title: "Patient graph context",
    description: "Read-only knowledge-graph context for a patient.",
    role: "read_only",
    fields: [
      patientField,
      { name: "include_claims", label: "Include claims", type: "boolean", default: true },
      { name: "include_interactions", label: "Include interactions", type: "boolean", default: true },
    ],
  },
  {
    name: "vector_evidence_search",
    title: "Vector evidence search",
    description: "Semantic search over patient events (evidence text redacted for read-only).",
    role: "read_only",
    fields: [questionField, optionalPatient, { name: "top_k", label: "Top K", type: "number", default: 5, min: 1, max: 20 }],
  },
  {
    name: "evidence_bundle_export",
    title: "Evidence bundle export",
    description: "Bounded evidence bundle for audit/export workflows.",
    role: "export",
    fields: [questionField, optionalPatient],
  },
  {
    name: "skills_plan_get",
    title: "Skills plan",
    description: "Plan which agent skills apply to a business goal.",
    role: "read_only",
    fields: [
      {
        name: "business_goal",
        label: "Business goal",
        type: "select",
        required: true,
        default: "medication_safety_review",
        // Mirrors business_goals in agent-service/src/healthcare_agent/config/skills_layer.json.
        options: ["clinical_deterioration_triage", "medication_safety_review", "claims_denial_prevention"],
      },
      { name: "agent", label: "Agent (optional)", type: "text", default: "" },
    ],
  },
];

export type ToolArgs = Record<string, string | number | boolean>;

export function defaultArgs(spec: ToolSpec): ToolArgs {
  const args: ToolArgs = {};
  for (const f of spec.fields) {
    args[f.name] = f.default ?? (f.type === "boolean" ? false : f.type === "number" ? 0 : "");
  }
  return args;
}

/** Validates and coerces form values; returns an error message or the argument object. */
export function buildToolArgs(spec: ToolSpec, values: ToolArgs): { ok: true; args: ToolArgs } | { ok: false; error: string } {
  const args: ToolArgs = {};
  for (const f of spec.fields) {
    const raw = values[f.name];
    if (f.type === "boolean") {
      args[f.name] = raw === true;
      continue;
    }
    if (f.type === "number") {
      const n = typeof raw === "number" ? raw : Number(raw);
      if (!Number.isFinite(n)) return { ok: false, error: `${f.label} must be a number.` };
      if (f.min !== undefined && n < f.min) return { ok: false, error: `${f.label} must be ≥ ${f.min}.` };
      if (f.max !== undefined && n > f.max) return { ok: false, error: `${f.label} must be ≤ ${f.max}.` };
      args[f.name] = Math.trunc(n);
      continue;
    }
    const text = String(raw ?? "").trim();
    if (f.required && !text) return { ok: false, error: `${f.label} is required.` };
    if (f.type === "select" && text && f.options && !f.options.includes(text)) {
      return { ok: false, error: `${f.label} must be one of: ${f.options.join(", ")}.` };
    }
    args[f.name] = text;
  }
  return { ok: true, args };
}
