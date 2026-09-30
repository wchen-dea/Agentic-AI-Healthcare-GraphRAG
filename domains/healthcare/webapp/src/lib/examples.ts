export interface ExampleQuery {
  title: string;
  question: string;
  patientId: string;
}

export const EXAMPLE_QUERIES: ExampleQuery[] = [
  {
    title: "Polypharmacy safety review",
    patientId: "patient-0001",
    question:
      "Review medication safety: are there dangerous interactions or contraindications for this patient given their current labs and conditions?",
  },
  {
    title: "Hyperkalemia contraindication chain",
    patientId: "patient-0001",
    question:
      "This patient has elevated potassium. Are any current medications contraindicated for hyperkalemia? Trace the causal chain from lab result to condition to contraindication rule.",
  },
  {
    title: "Dual RAAS blockade check",
    patientId: "patient-0001",
    question:
      "Is this patient on both an ACE inhibitor and a potassium-sparing diuretic? What is the interaction risk, severity, and mechanism?",
  },
  {
    title: "Multi-condition polypharmacy",
    patientId: "patient-0050",
    question:
      "Provide a comprehensive safety assessment: interactions, contraindications, lab-confirmed risks, and adverse reaction history for this polypharmacy patient.",
  },
  {
    title: "Adverse reaction correlation",
    patientId: "patient-0003",
    question:
      "The patient's clinical notes mention dizziness and nausea. Cross-reference these symptoms against known adverse reactions for all active medications.",
  },
  {
    title: "Steroid-insulin conflict",
    patientId: "patient-0015",
    question:
      "This patient is on both a corticosteroid and insulin. Does the graph show a hyperglycemia interaction risk? Confirm with lab glucose or HbA1c signals.",
  },
];

export const SAMPLE_PATIENTS = ["patient-0001", "patient-0003", "patient-0015", "patient-0050"];
