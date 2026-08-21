FROM python:3.11-slim
WORKDIR /app
COPY data-platform/supply-chain/flink-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY data-platform/supply-chain/flink-app/app /app/app
COPY data-platform/supply-chain/flink-app/supplychain_graph_rag_job.py /app/supplychain_graph_rag_job.py
COPY data-platform/shared /app/shared_lib
CMD ["python", "supplychain_graph_rag_job.py"]
