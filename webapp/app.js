const form = document.getElementById("queryForm");
const apiModeInput = document.getElementById("apiMode");
const apiBaseInput = document.getElementById("apiBase");
const patientIdInput = document.getElementById("patientId");
const questionInput = document.getElementById("question");
const answerEl = document.getElementById("answer");
const vectorEl = document.getElementById("vectorContext");
const graphEl = document.getElementById("graphContext");
const submitBtn = document.getElementById("submitBtn");

const MCP_PROTOCOL_VERSION = "2025-03-26";
const MCP_CLIENT_INFO = { name: "provider-web", version: "0.1.0" };

const savedApiBase = localStorage.getItem("provider_rag_api_base");
if (savedApiBase) {
  apiBaseInput.value = savedApiBase;
}

const savedApiMode = localStorage.getItem("provider_api_mode");
if (savedApiMode === "mcp" || savedApiMode === "rag") {
  apiModeInput.value = savedApiMode;
}

function parseSseFirstJson(payloadText) {
  const lines = payloadText.split(/\r?\n/);
  for (const line of lines) {
    if (!line.startsWith("data: ")) {
      continue;
    }
    const jsonText = line.slice(6).trim();
    if (!jsonText) {
      continue;
    }
    try {
      return JSON.parse(jsonText);
    } catch {
      // Keep scanning in case there are non-JSON data lines.
    }
  }
  throw new Error("No JSON payload found in SSE response.");
}

async function readFirstMcpEventAsJson(response, timeoutMs = 45000) {
  if (!response.body || !response.body.getReader) {
    const text = await response.text();
    return parseSseFirstJson(text);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  const startedAt = Date.now();

  try {
    while (true) {
      if (Date.now() - startedAt > timeoutMs) {
        throw new Error("Timed out waiting for MCP event.");
      }

      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      try {
        const parsed = parseSseFirstJson(buffer);
        return parsed;
      } catch {
        // Need more chunks.
      }
    }
  } finally {
    try {
      await reader.cancel();
    } catch {
      // Ignore reader cancellation failures.
    }
  }

  throw new Error("MCP response ended before a JSON event was received.");
}

function normalizeMcpToolPayload(result) {
  if (!result) {
    return { answer: "No MCP tool result returned.", vector_context: [], graph_context: [] };
  }

  if (result.structuredContent && typeof result.structuredContent === "object") {
    return result.structuredContent;
  }

  if (Array.isArray(result.content)) {
    const textParts = result.content
      .filter((item) => item && item.type === "text" && typeof item.text === "string")
      .map((item) => item.text);
    if (textParts.length > 0) {
      const merged = textParts.join("\n").trim();
      try {
        return JSON.parse(merged);
      } catch {
        return { answer: merged, vector_context: [], graph_context: [] };
      }
    }
  }

  return result;
}

async function runMcpQuery(apiBase, question, patientId) {
  const endpoint = `${apiBase}/mcp`;

  const initRequest = {
    jsonrpc: "2.0",
    id: "web-init-1",
    method: "initialize",
    params: {
      protocolVersion: MCP_PROTOCOL_VERSION,
      capabilities: {},
      clientInfo: MCP_CLIENT_INFO
    }
  };

  const initResp = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream"
    },
    body: JSON.stringify(initRequest)
  });

  if (!initResp.ok) {
    const body = await initResp.text();
    throw new Error(`MCP initialize failed (HTTP ${initResp.status}): ${body}`);
  }

  const sessionId = initResp.headers.get("mcp-session-id");
  if (!sessionId) {
    throw new Error("MCP initialize did not return mcp-session-id.");
  }

  const initJson = await readFirstMcpEventAsJson(initResp);
  if (initJson.error) {
    throw new Error(`MCP initialize error: ${initJson.error.message || "unknown"}`);
  }

  const initializedNotification = {
    jsonrpc: "2.0",
    method: "notifications/initialized",
    params: {}
  };

  const initializedResp = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "MCP-Session-Id": sessionId
    },
    body: JSON.stringify(initializedNotification)
  });

  if (!initializedResp.ok) {
    const body = await initializedResp.text();
    throw new Error(`MCP initialized notification failed (HTTP ${initializedResp.status}): ${body}`);
  }

  const callRequest = {
    jsonrpc: "2.0",
    id: "web-tool-1",
    method: "tools/call",
    params: {
      name: "graphrag_answer_generate",
      arguments: {
        question,
        patient_id: patientId || null,
        response_style: "concise"
      }
    }
  };

  const callResp = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json, text/event-stream",
      "MCP-Session-Id": sessionId
    },
    body: JSON.stringify(callRequest)
  });

  if (!callResp.ok) {
    const body = await callResp.text();
    throw new Error(`MCP tools/call failed (HTTP ${callResp.status}): ${body}`);
  }

  const callJson = await readFirstMcpEventAsJson(callResp);
  if (callJson.error) {
    throw new Error(`MCP tools/call error: ${callJson.error.message || "unknown"}`);
  }

  const normalized = normalizeMcpToolPayload(callJson.result || {});
  return {
    answer: normalized.answer || "No answer returned.",
    vector_context: normalized.vector_context || [],
    graph_context: normalized.graph_context || []
  };
}

async function runRagQuery(apiBase, payload) {
  const response = await fetch(`${apiBase}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Caller-Role": "generation"
    },
    body: JSON.stringify(payload)
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`HTTP ${response.status}: ${body}`);
  }

  return response.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
  const apiMode = apiModeInput.value;
  const patientId = patientIdInput.value.trim();
  const question = questionInput.value.trim();

  if (!apiBase || !question) {
    return;
  }

  localStorage.setItem("provider_rag_api_base", apiBase);
  localStorage.setItem("provider_api_mode", apiMode);

  submitBtn.disabled = true;
  submitBtn.textContent = "Running...";
  answerEl.textContent = apiMode === "mcp" ? "Running MCP tool..." : "Running query...";
  vectorEl.textContent = "[]";
  graphEl.textContent = "[]";

  const payload = { question };
  if (patientId) {
    payload.patient_id = patientId;
  }

  try {
    const data =
      apiMode === "mcp"
        ? await runMcpQuery(apiBase, question, patientId)
        : await runRagQuery(apiBase, payload);

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
