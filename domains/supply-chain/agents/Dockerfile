FROM python:3.11-slim
WORKDIR /app
COPY domains/supply-chain/agents/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/supply-chain/agents/app.py .
COPY domains/supply-chain/agents/llm_provider.py .
COPY domains/supply-chain/agents/skills_layer.py .
COPY domains/supply-chain/agents/domain ./domain
COPY domains/supply-chain/agents/config ./config
COPY platform/shared ./shared_lib
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
