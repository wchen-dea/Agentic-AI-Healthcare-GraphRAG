FROM python:3.11-slim
WORKDIR /app
COPY rag-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY rag-api/app.py .
COPY rag-api/llm_provider.py .
COPY rag-api/skills_layer.py .
COPY rag-api/domain ./domain
COPY rag-api/config ./config
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
