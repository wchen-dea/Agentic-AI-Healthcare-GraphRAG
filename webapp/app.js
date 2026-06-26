const form = document.getElementById("queryForm");
const apiBaseInput = document.getElementById("apiBase");
const patientIdInput = document.getElementById("patientId");
const questionInput = document.getElementById("question");
const answerEl = document.getElementById("answer");
const vectorEl = document.getElementById("vectorContext");
const graphEl = document.getElementById("graphContext");
const submitBtn = document.getElementById("submitBtn");

const savedApiBase = localStorage.getItem("provider_rag_api_base");
if (savedApiBase) {
  apiBaseInput.value = savedApiBase;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const apiBase = apiBaseInput.value.trim().replace(/\/$/, "");
  const patientId = patientIdInput.value.trim();
  const question = questionInput.value.trim();

  if (!apiBase || !question) {
    return;
  }

  localStorage.setItem("provider_rag_api_base", apiBase);

  submitBtn.disabled = true;
  submitBtn.textContent = "Running...";
  answerEl.textContent = "Running query...";
  vectorEl.textContent = "[]";
  graphEl.textContent = "[]";

  const payload = { question };
  if (patientId) {
    payload.patient_id = patientId;
  }

  try {
    const response = await fetch(`${apiBase}/query`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`HTTP ${response.status}: ${body}`);
    }

    const data = await response.json();
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
