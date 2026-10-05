import { useEffect, useState, type FormEvent } from "react";
import { writePatientMemory } from "../api/client";

interface Props {
  apiBase: string;
  patientId?: string;
  answer?: string;
}

export function PatientMemoryPanel({ apiBase, patientId: sourcePatientId, answer }: Props) {
  const [patientId, setPatientId] = useState("");
  const [key, setKey] = useState("");
  const [value, setValue] = useState("");
  const [provenance, setProvenance] = useState("clinician_note");
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!answer?.trim()) return;
    if (sourcePatientId?.trim()) setPatientId(sourcePatientId.trim());
    setKey("clinical_summary");
    setValue(answer.trim().slice(0, 1000));
    setProvenance("clinician_note");
    setConsent(false);
    setStatus("Answer loaded for review. Confirm consent before saving.");
  }, [answer, sourcePatientId]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus(null);
    setError(null);

    if (!patientId.trim() || !key.trim() || !value.trim()) {
      setError("Patient ID, fact key, and fact value are required.");
      return;
    }
    if (!consent) {
      setError("Explicit consent is required before storing patient memory.");
      return;
    }

    setBusy(true);
    try {
      const result = await writePatientMemory(apiBase, {
        patient_id: patientId.trim(),
        facts: [{ key: key.trim(), value: value.trim(), source_type: provenance }],
        provenance: { source: provenance, entered_via: "provider_web" },
        consent: true,
      }).promise;
      setStatus(`Stored ${result.fact_count} fact(s) for ${result.patient_id}.`);
      setKey("");
      setValue("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to store patient memory.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="memory-panel" onSubmit={submit} aria-label="Governed patient memory">
      <h3>Governed patient memory</h3>
      <p className="muted small">Store minimized facts only. Consent and clinical review are required.</p>
      <label className="field" htmlFor="memory-patient-id">
        <span>Patient ID</span>
        <input id="memory-patient-id" value={patientId} onChange={(e) => setPatientId(e.target.value)} placeholder="demo-us-001" />
      </label>
      <label className="field" htmlFor="memory-key">
        <span>Fact</span>
        <input id="memory-key" value={key} onChange={(e) => setKey(e.target.value)} placeholder="allergy" />
      </label>
      <label className="field" htmlFor="memory-value">
        <span>Value</span>
        <input id="memory-value" value={value} onChange={(e) => setValue(e.target.value)} placeholder="penicillin" />
      </label>
      <label className="field" htmlFor="memory-provenance">
        <span>Provenance</span>
        <select id="memory-provenance" value={provenance} onChange={(e) => setProvenance(e.target.value)}>
          <option value="clinician_note">Clinician note</option>
          <option value="discharge_summary">Discharge summary</option>
          <option value="medication_list">Medication list</option>
          <option value="patient_report">Patient report</option>
        </select>
      </label>
      <label className="check">
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        Patient consent confirmed
      </label>
      {error && <p className="form-error" role="alert">{error}</p>}
      {status && <p className="form-success" role="status">{status}</p>}
      <button type="submit" className="btn btn-primary" disabled={busy || !consent}>
        {busy ? "Saving…" : "Save governed memory"}
      </button>
    </form>
  );
}