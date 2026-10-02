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
  {
    title: "Renal and electrolyte lab trend",
    patientId: "patient-0001",
    question:
      "Interpret this patient's recent lab results: how do potassium, creatinine, and eGFR trend over time, and which values are outside reference ranges?",
  },
  {
    title: "Claim coding review",
    patientId: "patient-0050",
    question:
      "Review the ICD and CPT coding on this patient's recent claims. Are any codes unsupported by documented conditions or at risk of denial?",
  },
  {
    title: "High-risk cohort triage",
    patientId: "patient-0003",
    question:
      "Across the cohort, which patients share this patient's chronic conditions, and who should be prioritized for outreach?",
  },
  {
    title: "Longitudinal patient summary",
    patientId: "patient-0015",
    question:
      "Summarize this patient's clinical history: active conditions, recent encounters, and key care gaps, citing source evidence.",
  },
  {
    title: "CKD + hyperkalemia contraindication loop",
    patientId: "patient-0068",
    question:
      "Given this patient's CKD and hyperkalemia, are any current medications contraindicated? Check renal function (eGFR/creatinine) and potassium before concluding.",
  },
  {
    title: "Bleeding risk with anemia labs",
    patientId: "patient-0019",
    question:
      "Assess bleeding risk: do any current medications interact or carry contraindications that raise bleeding risk? Confirm against hemoglobin/hematocrit and other anemia labs before concluding.",
  },
  {
    title: "Opioid + gabapentin with reduced renal function",
    patientId: "patient-0025",
    question:
      "This patient is on an opioid and gabapentin. Given reduced kidney function, are there contraindications or CNS-depression interactions? Verify eGFR/creatinine and recommend dose considerations.",
  },
  {
    title: "Nephrotoxic polypharmacy",
    patientId: "patient-0011",
    question:
      "Is this patient receiving furosemide together with vancomycin? Evaluate the nephrotoxic interaction risk, confirm with creatinine and eGFR trends, and list related contraindications.",
  },
  {
    title: "Cohort urgent follow-up triage",
    patientId: "patient-0068",
    question:
      "Triage the cohort: which patients need urgent follow-up? Start from this patient's renal and potassium risk profile.",
  },
];

export const SAMPLE_PATIENTS = [
  "patient-0001",
  "patient-0003",
  "patient-0015",
  "patient-0050",
  "patient-0068",
  "patient-0019",
  "patient-0025",
  "patient-0011",
];
