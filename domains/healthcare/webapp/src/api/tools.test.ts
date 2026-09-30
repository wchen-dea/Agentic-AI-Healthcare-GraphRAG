import { describe, expect, it } from "vitest";
import { MCP_TOOLS, buildToolArgs, defaultArgs } from "./tools";

const byName = (name: string) => {
  const spec = MCP_TOOLS.find((t) => t.name === name);
  if (!spec) throw new Error(`missing ${name}`);
  return spec;
};

describe("buildToolArgs", () => {
  it("requires required text fields", () => {
    const spec = byName("medication_risk_assess");
    expect(buildToolArgs(spec, { patient_id: "  " })).toEqual({ ok: false, error: "Patient ID is required." });
  });

  it("trims text and truncates numbers", () => {
    const spec = byName("risk_summary_generate");
    expect(buildToolArgs(spec, { patient_id: " patient-0001 ", time_window_hours: "48.9" })).toEqual({
      ok: true,
      args: { patient_id: "patient-0001", time_window_hours: 48 },
    });
  });

  it("enforces numeric bounds", () => {
    const spec = byName("risk_summary_generate");
    const r = buildToolArgs(spec, { patient_id: "p", time_window_hours: 5000 });
    expect(r.ok).toBe(false);
  });

  it("defaults cover every field", () => {
    for (const spec of MCP_TOOLS) {
      expect(Object.keys(defaultArgs(spec)).sort()).toEqual(spec.fields.map((f) => f.name).sort());
    }
  });
});

describe("select fields", () => {
  it("rejects values outside the server-side enum", () => {
    const spec = byName("skills_plan_get");
    expect(buildToolArgs(spec, { business_goal: "free text" }).ok).toBe(false);
    expect(buildToolArgs(spec, { business_goal: "medication_safety_review", agent: "" })).toEqual({
      ok: true,
      args: { business_goal: "medication_safety_review", agent: "" },
    });
  });
});

describe("server contract drift", () => {
  it("business_goal options mirror agents/config/skills_layer.json", async () => {
    const { readFile } = await import("node:fs/promises");
    const raw = await readFile(new URL("../../../agents/config/skills_layer.json", import.meta.url), "utf8");
    const goals = Object.keys((JSON.parse(raw) as { business_goals: Record<string, unknown> }).business_goals);
    const field = byName("skills_plan_get").fields.find((f) => f.name === "business_goal");
    expect([...(field?.options ?? [])].sort()).toEqual([...goals].sort());
  });
});
