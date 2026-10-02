import { describe, expect, it } from "vitest";
import { buildGraph, countByKind } from "./graph";

const context = [
  {
    patient_id: "patient-0001",
    conditions: ["Chronic kidney disease", { name: "Hypertension" }],
    medications: [{ medication: "Lisinopril" }, "Ibuprofen"],
    observations: [{ name: "Creatinine", abnormal: true }],
    symptoms: ["Fatigue"],
    interactions: [{ from: "Lisinopril", to: "Ibuprofen", risk: "AKI", severity: "high" }],
    contraindications: [{ medication: "Ibuprofen", condition: "Chronic kidney disease", reason: "renal" }],
    lab_signals: [{ observation: "Creatinine", indicated_condition: "Chronic kidney disease", reason: "elevated" }],
    adverse_events: [{ symptom: "Nausea", medication: "Lisinopril", severity: "low" }],
  },
];

describe("buildGraph", () => {
  const model = buildGraph(context);

  it("deduplicates nodes across relationship types", () => {
    expect(countByKind(model)).toEqual({
      patient: 1,
      condition: 2,
      medication: 2,
      observation: 1,
      symptom: 1,
      adverse_event: 1,
    });
  });

  it("creates typed clinical edges", () => {
    const kinds = new Set(model.edges.map((e) => e.kind));
    for (const k of ["has_condition", "takes", "has_observation", "has_symptom", "interaction", "contraindication", "lab_signal", "adverse_event"]) {
      expect(kinds.has(k as never)).toBe(true);
    }
    const interaction = model.edges.find((e) => e.kind === "interaction");
    expect(interaction?.severity).toBe("high");
    expect(interaction?.label).toBe("AKI");
  });

  it("flags risky nodes and lays out deterministically", () => {
    expect(model.nodes.find((n) => n.label === "Ibuprofen")?.flagged).toBe(true);
    expect(buildGraph(context).nodes.map((n) => [n.x, n.y])).toEqual(model.nodes.map((n) => [n.x, n.y]));
    const patient = model.nodes.find((n) => n.kind === "patient");
    expect(patient).toMatchObject({ x: 400, y: 280 });
  });

  it("ignores entities without a patient id", () => {
    expect(buildGraph([{ conditions: ["x"] }]).nodes).toEqual([]);
  });
});
