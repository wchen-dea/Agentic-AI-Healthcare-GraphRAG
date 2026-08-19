// Supply-chain domain query wiring.
initQueryForm({
  buildPayload(question) {
    const entityId = document.getElementById("entityId").value.trim();
    const payload = { question };
    if (entityId) payload.entity_id = entityId;
    return payload;
  },
  mcpTool: "graphrag_answer_generate",
  mcpArgsBuilder(question) {
    const entityId = document.getElementById("entityId").value.trim();
    return { question, entity_id: entityId || null, response_style: "concise" };
  }
});
