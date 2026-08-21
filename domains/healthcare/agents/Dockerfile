FROM python:3.11-slim
WORKDIR /app
COPY domains/healthcare/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/healthcare/agents/app.py .
COPY domains/healthcare/agents/llm_provider.py .
COPY domains/healthcare/agents/skills_layer.py .
COPY domains/healthcare/agents/domain ./domain
COPY domains/healthcare/agents/langgraph_agents ./langgraph_agents
COPY domains/healthcare/agents/config ./config
COPY data-platform/shared ./shared_lib
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
