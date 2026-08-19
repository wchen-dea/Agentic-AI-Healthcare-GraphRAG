FROM python:3.11-slim
WORKDIR /app
COPY domains/supply-chain/rag-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/supply-chain/rag-api/app.py .
COPY domains/supply-chain/rag-api/llm_provider.py .
COPY domains/supply-chain/rag-api/skills_layer.py .
COPY domains/supply-chain/rag-api/domain ./domain
COPY domains/supply-chain/rag-api/config ./config
COPY shared_lib ./shared_lib
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
