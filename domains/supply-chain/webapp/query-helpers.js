// Shared RAG/MCP query helpers used by all domain webapps.

const MCP_PROTOCOL_VERSION = "2025-03-26";
const MCP_CLIENT_INFO = { name: "domain-web", version: "0.2.0" };

function parseSseFirstJson(payloadText) {
  const lines = payloadText.split(/\r?\n/);
  for (const line of lines) {
    if (!line.startsWith("data: ")) continue;
    const jsonText = line.slice(6).trim();
    if (!jsonText) continue;
    try { return JSON.parse(jsonText); } catch { /* keep scanning */ }
  }
  throw new Error("No JSON payload found in SSE response.");
}

async function readFirstMcpEventAsJson(response, timeoutMs = 45000) {
  if (!response.body || !response.body.getReader) {
    return parseSseFirstJson(await response.text());
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const start = Date.now();
  try {
    while (true) {
      if (Date.now() - start > timeoutMs) throw new Error("Timed out waiting for MCP event.");
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      try { return parseSseFirstJson(buffer); } catch { /* need more */ }
    }
  } finally { try { await reader.cancel(); } catch { /* ignore */ } }
  throw new Error("MCP response ended before a JSON event was received.");
}

function normalizeMcpToolPayload(result) {
  if (!result) return { answer: "No MCP tool result returned.", vector_context: [], graph_context: [] };
  if (result.structuredContent && typeof result.structuredContent === "object") return result.structuredContent;
  if (Array.isArray(result.content)) {
    const text = result.content.filter(i => i && i.type === "text" && typeof i.text === "string").map(i => i.text);
    if (text.length > 0) {
      const merged = text.join("\n").trim();
      try { return JSON.parse(merged); } catch { return { answer: merged, vector_context: [], graph_context: [] }; }
    }
  }
  return result;
}

async function runMcpQuery(apiBase, toolName, toolArgs) {
  const endpoint = `${apiBase}/mcp`;
  const initResp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream" },
    body: JSON.stringify({ jsonrpc: "2.0", id: "web-init-1", method: "initialize", params: { protocolVersion: MCP_PROTOCOL_VERSION, capabilities: {}, clientInfo: MCP_CLIENT_INFO } })
  });
  if (!initResp.ok) throw new Error(`MCP initialize failed (HTTP ${initResp.status})`);
  const sessionId = initResp.headers.get("mcp-session-id");
  if (!sessionId) throw new Error("MCP initialize did not return mcp-session-id.");
  const initJson = await readFirstMcpEventAsJson(initResp);
  if (initJson.error) throw new Error(`MCP init error: ${initJson.error.message}`);

  await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream", "MCP-Session-Id": sessionId },
    body: JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized", params: {} })
  });

  const callResp = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json, text/event-stream", "MCP-Session-Id": sessionId },
    body: JSON.stringify({ jsonrpc: "2.0", id: "web-tool-1", method: "tools/call", params: { name: toolName, arguments: toolArgs } })
  });
  if (!callResp.ok) throw new Error(`MCP tools/call failed (HTTP ${callResp.status})`);
  const callJson = await readFirstMcpEventAsJson(callResp);
  if (callJson.error) throw new Error(`MCP error: ${callJson.error.message}`);
  const normalized = normalizeMcpToolPayload(callJson.result || {});
  return {
    ...normalized,
    answer: normalized.answer || "No answer.",
    vector_context: normalized.vector_context || [],
    graph_context: normalized.graph_context || []
  };
}

async function runRagQuery(apiBase, payload) {
  const response = await fetch(`${apiBase}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Caller-Role": "generation" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  return response.json();
}

// ---------- Rendering helpers (progressive enhancement; safe no-ops on older/simpler pages) ----------

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function humanizeKey(key) {
  return String(key || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function severityClass(sev) {
  const s = String(sev || "").toLowerCase();
  if (s === "high") return "sev-high";
  if (s === "moderate") return "sev-moderate";
  if (s === "low") return "sev-low";
  return "sev-unknown";
}

// Evidence text is redacted-by-default for non-export callers; the API marks
// this with a `text_redacted: true` boolean rather than returning any text.
function evidenceText(item) {
  if (item.text) return item.text;
  if (item.text_redacted) return "Evidence text withheld for this access role.";
  return "(no text available)";
}

function renderVectorContext(container, items, countEl) {
  if (!container) return;
  const list = items || [];
  if (countEl) countEl.textContent = list.length ? `(${list.length})` : "";
  if (container.tagName === "PRE") {
    container.textContent = JSON.stringify(list, null, 2);
    return;
  }
  if (!list.length) {
    container.innerHTML = '<p class="empty-state">No vector evidence returned.</p>';
    return;
  }
  container.innerHTML = list.map((item) => {
    const score = typeof item.score === "number" ? item.score : null;
    const pct = score !== null ? Math.max(0, Math.min(100, Math.round(score * 100))) : null;
    return `
      <article class="evidence-card">
        <div class="evidence-card-head">
          ${item.event_type ? `<span class="badge badge-neutral">${escapeHtml(item.event_type)}</span>` : ""}
          ${item.patient_id ? `<span class="chip">${escapeHtml(item.patient_id)}</span>` : ""}
          ${pct !== null ? `
            <span class="score" title="Relevance score">
              <span class="score-bar"><span class="score-fill" style="width:${pct}%"></span></span>
              ${pct}%
            </span>` : ""}
        </div>
        <p class="evidence-text">${escapeHtml(evidenceText(item))}</p>
      </article>`;
  }).join("");
}

// Recursively render an arbitrary JSON value (graph context fields vary by domain/entity).
function renderGraphValue(value) {
  if (value === null || value === undefined || value === "") {
    return '<span class="text-faint">&mdash;</span>';
  }
  if (Array.isArray(value)) {
    if (!value.length) return '<span class="text-faint">None</span>';
    if (value.every((v) => v === null || typeof v !== "object")) {
      return `<div class="chip-row">${value.map((v) => `<span class="chip">${escapeHtml(v)}</span>`).join("")}</div>`;
    }
    return `<div class="mini-list">${value.map((v) => `<div class="mini-list-item">${renderGraphValue(v)}</div>`).join("")}</div>`;
  }
  if (typeof value === "object") {
    return `<div class="kv-grid">${Object.entries(value).map(([k, v]) => `
        <span class="kv-key">${escapeHtml(humanizeKey(k))}</span>
        <span class="kv-val">${typeof v === "object" && v !== null ? renderGraphValue(v) : escapeHtml(v)}</span>
      `).join("")}</div>`;
  }
  return escapeHtml(value);
}

function renderGraphContext(container, items, countEl) {
  if (!container) return;
  const list = items || [];
  if (countEl) countEl.textContent = list.length ? `(${list.length})` : "";
  if (container.tagName === "PRE") {
    container.textContent = JSON.stringify(list, null, 2);
    return;
  }
  if (!list.length) {
    container.innerHTML = '<p class="empty-state">No graph context returned.</p>';
    return;
  }
  container.innerHTML = list.map((item) => {
    const { patient_id, entity_id, ...rest } = item;
    const sections = Object.entries(rest).filter(
      ([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && v.length === 0)
    );
    return `
      <article class="graph-card">
        <div class="graph-card-head">
          <h3>${escapeHtml(patient_id || entity_id || "Graph entity")}</h3>
        </div>
        ${sections.length
          ? sections.map(([key, value]) => `
            <div class="graph-section">
              <p class="graph-section-title">${escapeHtml(humanizeKey(key))}</p>
              ${renderGraphValue(value)}
            </div>`).join("")
          : '<p class="empty-state">No additional graph facts.</p>'}
      </article>`;
  }).join("");
}

function renderMeta(metaRow, data) {
  if (!metaRow) return;
  const badges = [];
  if (data.request_type) {
    badges.push({ id: "badgeRequestType", text: humanizeKey(data.request_type), cls: "badge-info" });
  }
  if (data.model_routing && data.model_routing.model) {
    const r = data.model_routing;
    badges.push({
      id: "badgeModel",
      text: `Model: ${r.model}${r.tier ? ` (${r.tier})` : ""}${r.downgraded ? " \u2193" : ""}`,
      cls: r.downgraded ? "badge-warning" : "badge-neutral"
    });
  }
  const conf = data.react && typeof data.react.confidence === "number"
    ? data.react.confidence
    : (data.structured_response && typeof data.structured_response.confidence === "number"
      ? data.structured_response.confidence
      : null);
  if (conf !== null) {
    badges.push({
      id: "badgeConfidence",
      text: `Confidence: ${Math.round(conf * 100)}%`,
      cls: conf >= 0.75 ? "badge-success" : conf >= 0.5 ? "badge-warning" : "badge-danger"
    });
  }
  if (data.retrieval_plan && data.retrieval_plan.name) {
    badges.push({ id: "badgePlan", text: `Plan: ${humanizeKey(data.retrieval_plan.name)}`, cls: "badge-neutral" });
  }

  let anyVisible = false;
  ["badgeRequestType", "badgeModel", "badgeConfidence", "badgePlan"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    const match = badges.find((b) => b.id === id);
    if (match) {
      el.textContent = match.text;
      el.className = `badge ${match.cls}`;
      el.hidden = false;
      anyVisible = true;
    } else {
      el.hidden = true;
    }
  });
  metaRow.hidden = !anyVisible;
}

function renderTrace(tracePanel, data) {
  if (!tracePanel) return;
  const parts = [];

  if (data.retrieval_plan) {
    const p = data.retrieval_plan;
    parts.push(`
      <div class="trace-section">
        <p class="graph-section-title">Retrieval Plan</p>
        <div class="kv-grid">
          <span class="kv-key">Name</span><span class="kv-val">${escapeHtml(humanizeKey(p.name || "\u2014"))}</span>
          <span class="kv-key">Top K</span><span class="kv-val">${escapeHtml(p.top_k ?? "\u2014")}</span>
          <span class="kv-key">Reason</span><span class="kv-val">${escapeHtml(p.reason || "\u2014")}</span>
        </div>
      </div>`);
  }

  if (data.guardrails) {
    parts.push(`
      <div class="trace-section">
        <p class="graph-section-title">Guardrails</p>
        ${renderGraphValue(data.guardrails)}
      </div>`);
  }

  if (data.model_routing) {
    parts.push(`
      <div class="trace-section">
        <p class="graph-section-title">Model Routing</p>
        ${renderGraphValue(data.model_routing)}
      </div>`);
  }

  if (data.react && Array.isArray(data.react.actions)) {
    const iterations = data.react.iterations ?? data.react.actions.length;
    parts.push(`
      <div class="trace-section">
        <p class="graph-section-title">Agent Reasoning (${iterations} iteration${iterations === 1 ? "" : "s"}, ${escapeHtml(humanizeKey(data.react.final_reason || ""))})</p>
        <ol class="timeline">
          ${data.react.actions.map((a) => `
            <li>
              <span class="timeline-marker"></span>
              <div class="timeline-body">
                <strong>Iteration ${(a.iteration ?? 0) + 1}</strong> &mdash; ${escapeHtml(humanizeKey(a.action || ""))}
                <div class="text-faint">plan: ${escapeHtml(a.plan_name || "\u2014")} &middot; top_k: ${escapeHtml(a.top_k ?? "\u2014")} &middot; +${a.new_event_ids ?? 0} evidence &middot; +${a.new_patient_ids ?? 0} patients &middot; confidence ${Math.round((a.confidence_after || 0) * 100)}%</div>
              </div>
            </li>`).join("")}
        </ol>
      </div>`);
  }

  const footerBits = [];
  if (data.trace_id) footerBits.push(`Trace ID: ${escapeHtml(data.trace_id)}`);
  if (data.retrieved_at) footerBits.push(`Retrieved: ${escapeHtml(data.retrieved_at)}`);
  if (footerBits.length) parts.push(`<p class="trace-footer">${footerBits.join(" &middot; ")}</p>`);

  tracePanel.innerHTML = parts.length ? parts.join("") : '<p class="empty-state">No trace metadata for this response.</p>';
}

function renderStructured(panel, structured) {
  if (!panel) return;
  if (!structured) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }
  panel.hidden = false;

  const findings = (structured.key_findings || []).map((f) => `<li>${escapeHtml(f)}</li>`).join("");
  const risks = (structured.risks || []).map((r) => `
    <div class="risk-card ${severityClass(r.severity)}">
      <div class="risk-card-head">
        <span class="badge ${severityClass(r.severity)}">${escapeHtml(r.severity || "unknown")}</span>
        <strong>${escapeHtml(humanizeKey(r.category || "risk"))}</strong>
      </div>
      <p>${escapeHtml(r.description || "")}</p>
      ${r.evidence_source ? `<p class="text-faint">Source: ${escapeHtml(humanizeKey(r.evidence_source))}</p>` : ""}
    </div>`).join("");
  const interactions = (structured.interactions || []).map((i) => `
    <div class="interaction-row">
      <span class="chip">${escapeHtml(i.drug_a || "?")}</span>
      <span class="text-faint">&times;</span>
      <span class="chip">${escapeHtml(i.drug_b || "?")}</span>
      <span class="badge ${severityClass(i.severity)}">${escapeHtml(i.severity || "unknown")}</span>
      ${i.mechanism ? `<span class="text-faint">${escapeHtml(i.mechanism)}</span>` : ""}
    </div>`).join("");
  const labs = (structured.lab_signals || []).map((l) => `
    <div class="lab-row">
      <strong>${escapeHtml(l.observation || "Observation")}</strong>
      ${l.value ? `<span class="chip">${escapeHtml(l.value)}</span>` : ""}
      ${l.indicated_condition ? `<span class="text-faint">&rarr; ${escapeHtml(l.indicated_condition)}</span>` : ""}
      ${l.reason ? `<p class="text-faint">${escapeHtml(l.reason)}</p>` : ""}
    </div>`).join("");

  const confPct = typeof structured.confidence === "number" ? Math.round(structured.confidence * 100) : null;

  panel.innerHTML = `
    ${structured.safety_caveat ? `<p class="safety-caveat">\u26a0 ${escapeHtml(structured.safety_caveat)}</p>` : ""}
    ${structured.summary ? `<p class="structured-summary">${escapeHtml(structured.summary)}</p>` : ""}
    ${confPct !== null ? `<div class="confidence-meter"><span class="score-bar"><span class="score-fill" style="width:${confPct}%"></span></span> Confidence ${confPct}%</div>` : ""}
    ${findings ? `<div class="trace-section"><p class="graph-section-title">Key Findings</p><ul class="findings-list">${findings}</ul></div>` : ""}
    ${risks ? `<div class="trace-section"><p class="graph-section-title">Risks</p>${risks}</div>` : ""}
    ${interactions ? `<div class="trace-section"><p class="graph-section-title">Interactions</p>${interactions}</div>` : ""}
    ${labs ? `<div class="trace-section"><p class="graph-section-title">Lab Signals</p>${labs}</div>` : ""}
  `;
}

// Tab switching is opt-in: pages without `.tab-btn` elements are unaffected.
function initTabs() {
  const tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
  if (!tabButtons.length) return;

  function activate(btn) {
    tabButtons.forEach((b) => {
      const active = b === btn;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", String(active));
      b.tabIndex = active ? 0 : -1;
    });
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.hidden = panel.id !== `panel-${btn.dataset.tab}`;
    });
  }

  tabButtons.forEach((btn, idx) => {
    btn.tabIndex = btn.classList.contains("is-active") ? 0 : -1;
    btn.addEventListener("click", () => activate(btn));
    btn.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight") { activate(tabButtons[(idx + 1) % tabButtons.length]); tabButtons[(idx + 1) % tabButtons.length].focus(); }
      if (e.key === "ArrowLeft") { activate(tabButtons[(idx - 1 + tabButtons.length) % tabButtons.length]); tabButtons[(idx - 1 + tabButtons.length) % tabButtons.length].focus(); }
    });
  });
}

if (typeof document !== "undefined") {
  document.addEventListener("DOMContentLoaded", initTabs);
}

// Domain webapps call this to wire up the form.
function initQueryForm({ buildPayload, mcpTool, mcpArgsBuilder }) {
  const form = document.getElementById("queryForm");
  const apiModeInput = document.getElementById("apiMode");
  const apiBaseInput = document.getElementById("apiBase");
  const questionInput = document.getElementById("question");
  const answerEl = document.getElementById("answer");
  const vectorEl = document.getElementById("vectorContext");
  const graphEl = document.getElementById("graphContext");
  const submitBtn = document.getElementById("submitBtn");
  const clearBtn = document.getElementById("clearBtn");
  const copyBtn = document.getElementById("copyAnswerBtn");
  const errorBanner = document.getElementById("errorBanner");
  const structuredPanel = document.getElementById("structuredPanel");
  const metaRow = document.getElementById("metaRow");
  const tracePanel = document.getElementById("tracePanel");
  const vectorCountEl = document.getElementById("vectorCount");
  const graphCountEl = document.getElementById("graphCount");
  const resultsEl = document.querySelector(".results");
  const connStatus = document.getElementById("connStatus");
  const connStatusText = document.getElementById("connStatusText");
  const checkConnBtn = document.getElementById("checkConnBtn");

  const savedBase = localStorage.getItem("rag_api_base");
  if (savedBase) apiBaseInput.value = savedBase;
  const savedMode = localStorage.getItem("rag_api_mode");
  if (savedMode === "mcp" || savedMode === "rag") apiModeInput.value = savedMode;

  function showError(message) {
    if (errorBanner) {
      errorBanner.textContent = message;
      errorBanner.hidden = false;
    } else {
      answerEl.textContent = message;
    }
  }

  function clearError() {
    if (errorBanner) {
      errorBanner.hidden = true;
      errorBanner.textContent = "";
    }
  }

  function resetResultPanels() {
    if (metaRow) metaRow.hidden = true;
    if (structuredPanel) { structuredPanel.hidden = true; structuredPanel.innerHTML = ""; }
    if (tracePanel) tracePanel.innerHTML = '<p class="empty-state">No trace yet.</p>';
    renderVectorContext(vectorEl, [], vectorCountEl);
    renderGraphContext(graphEl, [], graphCountEl);
  }

  if (clearBtn) {
    clearBtn.addEventListener("click", () => {
      questionInput.value = "";
      answerEl.textContent = "No query yet.";
      clearError();
      resetResultPanels();
      questionInput.focus();
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(answerEl.textContent || "");
        const original = copyBtn.textContent;
        copyBtn.textContent = "Copied!";
        setTimeout(() => { copyBtn.textContent = original; }, 1500);
      } catch {
        /* clipboard API unavailable; ignore */
      }
    });
  }

  if (checkConnBtn && connStatus) {
    checkConnBtn.addEventListener("click", async () => {
      const apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
      connStatus.dataset.state = "checking";
      if (connStatusText) connStatusText.textContent = "Checking...";
      try {
        const resp = await fetch(`${apiBase}/health`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        connStatus.dataset.state = "ok";
        if (connStatusText) connStatusText.textContent = "Connected";
      } catch {
        connStatus.dataset.state = "error";
        if (connStatusText) connStatusText.textContent = "Unreachable";
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
    const apiMode = apiModeInput.value;
    const question = questionInput.value.trim();
    if (!apiBase || !question) return;

    localStorage.setItem("rag_api_base", apiBase);
    localStorage.setItem("rag_api_mode", apiMode);

    clearError();
    submitBtn.disabled = true;
    submitBtn.textContent = "Running...";
    if (resultsEl) resultsEl.classList.add("is-loading");
    answerEl.textContent = apiMode === "mcp" ? "Running MCP tool..." : "Running query...";
    resetResultPanels();

    try {
      const data = apiMode === "mcp"
        ? await runMcpQuery(apiBase, mcpTool, mcpArgsBuilder(question))
        : await runRagQuery(apiBase, buildPayload(question));
      answerEl.textContent = data.answer || "No answer returned.";
      renderVectorContext(vectorEl, data.vector_context || [], vectorCountEl);
      renderGraphContext(graphEl, data.graph_context || [], graphCountEl);
      renderMeta(metaRow, data);
      renderTrace(tracePanel, data);
      renderStructured(structuredPanel, data.structured_response);
    } catch (err) {
      showError(`Request failed: ${err.message}`);
      answerEl.textContent = "Request failed. See details above.";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Run Query";
      if (resultsEl) resultsEl.classList.remove("is-loading");
    }
  });
}
