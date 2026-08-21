FROM python:3.11-slim
WORKDIR /app
COPY domains/healthcare/rag-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/healthcare/rag-api/app.py .
COPY domains/healthcare/rag-api/llm_provider.py .
COPY domains/healthcare/rag-api/skills_layer.py .
COPY domains/healthcare/rag-api/domain ./domain
COPY domains/healthcare/rag-api/langgraph_agents ./langgraph_agents
COPY domains/healthcare/rag-api/config ./config
COPY shared_lib ./shared_lib
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
