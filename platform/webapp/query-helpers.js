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
  return { answer: normalized.answer || "No answer.", vector_context: normalized.vector_context || [], graph_context: normalized.graph_context || [] };
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

  const savedBase = localStorage.getItem("rag_api_base");
  if (savedBase) apiBaseInput.value = savedBase;
  const savedMode = localStorage.getItem("rag_api_mode");
  if (savedMode === "mcp" || savedMode === "rag") apiModeInput.value = savedMode;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
    const apiMode = apiModeInput.value;
    const question = questionInput.value.trim();
    if (!apiBase || !question) return;

    localStorage.setItem("rag_api_base", apiBase);
    localStorage.setItem("rag_api_mode", apiMode);

    submitBtn.disabled = true;
    submitBtn.textContent = "Running...";
    answerEl.textContent = apiMode === "mcp" ? "Running MCP tool..." : "Running query...";
    vectorEl.textContent = "[]";
    graphEl.textContent = "[]";

    try {
      const data = apiMode === "mcp"
        ? await runMcpQuery(apiBase, mcpTool, mcpArgsBuilder(question))
        : await runRagQuery(apiBase, buildPayload(question));
      answerEl.textContent = data.answer || "No answer returned.";
      vectorEl.textContent = JSON.stringify(data.vector_context || [], null, 2);
      graphEl.textContent = JSON.stringify(data.graph_context || [], null, 2);
    } catch (err) {
      answerEl.textContent = `Request failed: ${err.message}`;
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Run Query";
    }
  });
}
