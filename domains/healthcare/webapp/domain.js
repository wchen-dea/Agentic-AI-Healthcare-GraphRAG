// Healthcare domain query wiring.
initQueryForm({
  buildPayload(question) {
    const patientId = document.getElementById("patientId").value.trim();
    const payload = { question };
    if (patientId) payload.patient_id = patientId;
    return payload;
  },
  mcpTool: "graphrag_answer_generate",
  mcpArgsBuilder(question) {
    const patientId = document.getElementById("patientId").value.trim();
    return { question, patient_id: patientId || null, response_style: "concise" };
  }
});
