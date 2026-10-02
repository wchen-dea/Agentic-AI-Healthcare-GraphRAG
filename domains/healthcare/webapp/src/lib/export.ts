// Pure serialisers for exporting a completed turn. The browser download lives in the UI layer.
import type { Turn } from "./conversation";
import { formatPercent, formatScore } from "./format";

export function turnToJson(turn: Turn): string {
  return JSON.stringify(
    {
      request: turn.request,
      status: turn.status,
      started_at: new Date(turn.startedAt).toISOString(),
      finished_at: turn.finishedAt ? new Date(turn.finishedAt).toISOString() : null,
      error: turn.error ?? null,
      response: turn.response ?? null,
    },
    null,
    2,
  );
}

function escapeCell(value: string): string {
  return value.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

export function turnToMarkdown(turn: Turn): string {
  const r = turn.response;
  const lines: string[] = [
    "# Healthcare GraphRAG result",
    "",
    `- **Question:** ${turn.request.question || "(tool call)"}`,
    "- **Mode:** RAG",
  ];
  if (turn.request.patientId) lines.push(`- **Patient:** ${turn.request.patientId}`);
  if (r?.trace_id) lines.push(`- **Trace ID:** ${r.trace_id}`);
  if (r?.retrieved_at) lines.push(`- **Retrieved at:** ${r.retrieved_at}`);
  lines.push("");

  if (turn.error) {
    lines.push("## Error", "", turn.error, "");
    return lines.join("\n");
  }
  if (!r) return lines.join("\n");

  lines.push("## Answer", "", r.answer || "(no answer)", "");

  const s = r.structured_response;
  if (s) {
    lines.push("## Structured summary", "", `Confidence: ${formatPercent(s.confidence)}`, "");
    if (s.key_findings.length) lines.push("### Key findings", "", ...s.key_findings.map((f) => `- ${f}`), "");
    if (s.risks.length) {
      lines.push("### Risks", "", "| Severity | Category | Description |", "| --- | --- | --- |");
      for (const risk of s.risks) {
        lines.push(`| ${risk.severity} | ${escapeCell(risk.category)} | ${escapeCell(risk.description)} |`);
      }
      lines.push("");
    }
    if (s.interactions.length) {
      lines.push("### Medication interactions", "");
      for (const i of s.interactions) lines.push(`- **${i.drug_a} ↔ ${i.drug_b}** (${i.severity}): ${i.mechanism}`);
      lines.push("");
    }
    if (s.safety_caveat) lines.push(`> ${s.safety_caveat}`, "");
  }

  if (r.vector_context.length) {
    lines.push("## Evidence", "", "| Score | Event | Patient | Type |", "| --- | --- | --- | --- |");
    for (const e of r.vector_context) {
      lines.push(
        `| ${formatScore(e.score)} | ${escapeCell(e.event_id ?? "—")} | ${escapeCell(e.patient_id ?? "—")} | ${escapeCell(e.event_type ?? "—")} |`,
      );
    }
    lines.push("");
  }

  lines.push(
    "---",
    "_Decision support only. Clinical review is required before acting on these results._",
    "",
  );
  return lines.join("\n");
}
