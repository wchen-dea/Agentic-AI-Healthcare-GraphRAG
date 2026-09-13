// Healthcare domain query wiring.
initQueryForm({
  buildPayload(question) {
    const patientId = document.getElementById("patientId").value.trim();
    const structuredMode = document.getElementById("structuredMode");
    const payload = { question, structured: Boolean(structuredMode && structuredMode.checked) };
    if (patientId) payload.patient_id = patientId;
    return payload;
  },
  mcpTool: "graphrag_answer_generate",
  mcpArgsBuilder(question) {
    const patientId = document.getElementById("patientId").value.trim();
    return { question, patient_id: patientId || null, response_style: "concise" };
  }
});

// Wire example query links to populate form fields.
document.querySelectorAll(".example-query").forEach(link => {
  link.addEventListener("click", e => {
    e.preventDefault();
    document.getElementById("question").value = link.dataset.question;
    document.getElementById("patientId").value = link.dataset.patient || "";
    document.getElementById("question").focus();
  });
});

// The `structured` flag is only understood by the RAG REST contract, not the MCP tool schema.
const apiModeSelect = document.getElementById("apiMode");
const structuredRow = document.getElementById("structuredToggleRow");
const structuredCheckbox = document.getElementById("structuredMode");

function syncStructuredAvailability() {
  if (!apiModeSelect || !structuredRow || !structuredCheckbox) return;
  const isMcp = apiModeSelect.value === "mcp";
  structuredRow.classList.toggle("is-disabled", isMcp);
  structuredCheckbox.disabled = isMcp;
}

if (apiModeSelect) {
  apiModeSelect.addEventListener("change", syncStructuredAvailability);
  syncStructuredAvailability();
}

