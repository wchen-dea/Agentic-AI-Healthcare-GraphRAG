import { useState, type FormEvent, type KeyboardEvent } from "react";
import { config } from "../config";
import type { TurnRequest } from "../lib/conversation";
import { EXAMPLE_QUERIES, SAMPLE_PATIENTS } from "../lib/examples";

interface Props {
  busy: boolean;
  onSubmit: (request: TurnRequest) => void;
  onCancel: () => void;
}

export function QueryPanel({ busy, onSubmit, onCancel }: Props) {
  const [question, setQuestion] = useState("");
  const [patientId, setPatientId] = useState("");
  const [topK, setTopK] = useState(5);
  const [structured, setStructured] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const trimmed = question.trim();

  const submit = () => {
    setError(null);
    if (busy) return;
    if (trimmed.length < 3) {
      setError("Question must be at least 3 characters.");
      return;
    }
    onSubmit({
      mode: "rag",
      question: trimmed,
      patientId: patientId.trim(),
      structured,
      topK,
    });
  };

  const onFormSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    } else if (event.key === "Escape" && busy) {
      onCancel();
    }
  };

  const applyExample = (questionText: string, examplePatientId: string) => {
    setQuestion(questionText);
    setPatientId(examplePatientId);
  };

  return (
    <form className="query-panel" onSubmit={onFormSubmit} aria-label="Clinical query">
      <datalist id="patient-suggestions">
        {SAMPLE_PATIENTS.map((patient) => (
          <option key={patient} value={patient} />
        ))}
      </datalist>

      <label className="field" htmlFor="patient-id">
        <span>Patient ID (optional)</span>
        <input
          id="patient-id"
          list="patient-suggestions"
          placeholder="patient-0001"
          value={patientId}
          onChange={(event) => setPatientId(event.target.value)}
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
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <small className="counter">
          {question.length}/{config.maxQuestionChars}
        </small>
      </label>

      <label className="field" htmlFor="top-k">
        <span>Evidence items</span>
        <input
          id="top-k"
          type="number"
          min={1}
          max={5}
          value={topK}
          onChange={(event) => setTopK(Math.min(5, Math.max(1, event.target.valueAsNumber || 1)))}
          onKeyDown={onKeyDown}
        />
      </label>

      <label className="check">
        <input type="checkbox" checked={structured} onChange={(event) => setStructured(event.target.checked)} />
        Structured clinical summary (risks, interactions, confidence)
      </label>

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {busy ? "Running…" : "Ask"}
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
          {EXAMPLE_QUERIES.map((example) => (
            <li key={example.title}>
              <button
                type="button"
                className="link"
                onClick={() => applyExample(example.question, example.patientId)}
              >
                {example.title}
              </button>
              <span className="muted"> · {example.patientId}</span>
            </li>
          ))}
        </ul>
      </details>
    </form>
  );
}