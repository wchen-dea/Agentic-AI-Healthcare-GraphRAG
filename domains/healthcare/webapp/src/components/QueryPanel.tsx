import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { config } from "../config";
import { buildToolArgs, defaultArgs, MCP_TOOLS, type ToolArgs, type ToolField } from "../api/tools";
import type { ApiMode } from "../api/types";
import type { TurnRequest } from "../lib/conversation";
import { EXAMPLE_QUERIES, SAMPLE_PATIENTS } from "../lib/examples";
import { humanizeKey } from "../lib/format";

interface Props {
  mode: ApiMode;
  busy: boolean;
  onSubmit: (request: TurnRequest) => void;
  onCancel: () => void;
}

const DEFAULT_TOOL = MCP_TOOLS[0]?.name ?? "graphrag_answer_generate";

function FieldInput({
  field,
  value,
  onChange,
  onKeyDown,
}: {
  field: ToolField;
  value: string | number | boolean | undefined;
  onChange: (v: string | number | boolean) => void;
  onKeyDown: (e: KeyboardEvent<HTMLElement>) => void;
}) {
  const id = `tool-${field.name}`;
  if (field.type === "boolean") {
    return (
      <label className="check" htmlFor={id}>
        <input id={id} type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />
        {field.label}
      </label>
    );
  }
  return (
    <label className="field" htmlFor={id}>
      <span>
        {field.label}
        {field.required && <span className="req"> *</span>}
      </span>
      {field.type === "select" ? (
        <select id={id} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)}>
          {!field.required && <option value="">—</option>}
          {(field.options ?? []).map((o) => (
            <option key={o} value={o}>
              {humanizeKey(o)}
            </option>
          ))}
        </select>
      ) : field.type === "textarea" ? (
        <textarea
          id={id}
          rows={3}
          maxLength={config.maxQuestionChars}
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={onKeyDown}
        />
      ) : (
        <input
          id={id}
          type={field.type === "number" ? "number" : "text"}
          list={field.name === "patient_id" ? "patient-suggestions" : undefined}
          min={field.min}
          max={field.max}
          placeholder={field.placeholder}
          value={typeof value === "boolean" || Number.isNaN(value) ? "" : (value ?? "")}
          onChange={(e) => onChange(field.type === "number" ? e.target.valueAsNumber : e.target.value)}
          onKeyDown={onKeyDown}
        />
      )}
    </label>
  );
}

export function QueryPanel({ mode, busy, onSubmit, onCancel }: Props) {
  const [question, setQuestion] = useState("");
  const [patientId, setPatientId] = useState("");
  const [structured, setStructured] = useState(true);
  const [toolName, setToolName] = useState(DEFAULT_TOOL);
  const [toolValues, setToolValues] = useState<Record<string, ToolArgs>>({});
  const [error, setError] = useState<string | null>(null);

  const tool = useMemo(() => MCP_TOOLS.find((t) => t.name === toolName) ?? MCP_TOOLS[0], [toolName]);
  const values: ToolArgs = tool ? { ...defaultArgs(tool), ...toolValues[tool.name] } : {};
  const trimmed = question.trim();

  const setToolValue = (name: string, v: string | number | boolean) => {
    if (!tool) return;
    setToolValues((prev) => ({ ...prev, [tool.name]: { ...values, [name]: v } }));
  };

  const submit = () => {
    setError(null);
    if (busy) return;
    if (mode === "rag") {
      if (trimmed.length < 3) {
        setError("Question must be at least 3 characters.");
        return;
      }
      onSubmit({ mode, question: trimmed, patientId: patientId.trim(), structured, tool: "query" });
      return;
    }
    if (!tool) return;
    const built = buildToolArgs(tool, values);
    if (!built.ok) {
      setError(built.error);
      return;
    }
    const q = built.args.question ?? built.args.business_goal ?? "";
    onSubmit({
      mode,
      question: typeof q === "string" ? q : "",
      patientId: typeof built.args.patient_id === "string" ? built.args.patient_id : "",
      structured: false,
      tool: tool.name,
      args: built.args,
    });
  };

  const onFormSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      submit();
    } else if (e.key === "Escape" && busy) {
      onCancel();
    }
  };

  const applyExample = (q: string, p: string) => {
    if (mode === "rag") {
      setQuestion(q);
      setPatientId(p);
    } else if (tool) {
      const next: ToolArgs = { ...values };
      if (tool.fields.some((f) => f.name === "question")) next.question = q;
      if (tool.fields.some((f) => f.name === "patient_id")) next.patient_id = p;
      setToolValues((prev) => ({ ...prev, [tool.name]: next }));
    }
  };

  return (
    <form className="query-panel" onSubmit={onFormSubmit} aria-label="Query">
      <datalist id="patient-suggestions">
        {SAMPLE_PATIENTS.map((p) => (
          <option key={p} value={p} />
        ))}
      </datalist>

      {mode === "rag" ? (
        <>
          <label className="field" htmlFor="patient-id">
            <span>Patient ID (optional)</span>
            <input
              id="patient-id"
              list="patient-suggestions"
              placeholder="patient-0001"
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              onKeyDown={onKeyDown}
            />
          </label>
          <label className="field" htmlFor="question">
            <span>Clinical question</span>
            <textarea
              id="question"
              rows={5}
              maxLength={config.maxQuestionChars}
              placeholder="Ask about medications, interactions, labs, risks…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={onKeyDown}
            />
            <small className="counter">
              {question.length}/{config.maxQuestionChars}
            </small>
          </label>
          <label className="check">
            <input type="checkbox" checked={structured} onChange={(e) => setStructured(e.target.checked)} />
            Structured clinical summary (risks, interactions, confidence)
          </label>
        </>
      ) : (
        tool && (
          <>
            <label className="field" htmlFor="tool-select">
              <span>MCP tool</span>
              <select id="tool-select" value={tool.name} onChange={(e) => setToolName(e.target.value)}>
                {MCP_TOOLS.map((t) => (
                  <option key={t.name} value={t.name}>
                    {t.title}
                  </option>
                ))}
              </select>
            </label>
            <p className="tool-desc">
              <span className={`badge role-${tool.role}`}>{tool.role.replace("_", "-")}</span> {tool.description}
            </p>
            {tool.fields.map((f) => (
              <FieldInput
                key={`${tool.name}-${f.name}`}
                field={f}
                value={values[f.name]}
                onChange={(v) => setToolValue(f.name, v)}
                onKeyDown={onKeyDown}
              />
            ))}
          </>
        )
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Running…" : mode === "rag" ? "Ask" : "Run tool"}
        </button>
        {busy && (
          <button type="button" className="btn" onClick={onCancel}>
            Cancel
          </button>
        )}
        <span className="hint">⌘/Ctrl + Enter to submit · Esc to cancel</span>
      </div>

      <details className="examples">
        <summary>Example clinical scenarios</summary>
        <ul>
          {EXAMPLE_QUERIES.map((ex) => (
            <li key={ex.title}>
              <button type="button" className="link" onClick={() => applyExample(ex.question, ex.patientId)}>
                {ex.title}
              </button>
              <span className="muted"> · {ex.patientId}</span>
            </li>
          ))}
        </ul>
      </details>
    </form>
  );
}
