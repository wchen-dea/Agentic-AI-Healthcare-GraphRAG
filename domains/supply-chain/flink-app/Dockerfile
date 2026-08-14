FROM python:3.11-slim
WORKDIR /app
COPY domains/supply-chain/flink-app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/supply-chain/flink-app/app /app/app
COPY domains/supply-chain/flink-app/supplychain_graph_rag_job.py /app/supplychain_graph_rag_job.py
COPY shared_lib /app/shared_lib
CMD ["python", "supplychain_graph_rag_job.py"]
