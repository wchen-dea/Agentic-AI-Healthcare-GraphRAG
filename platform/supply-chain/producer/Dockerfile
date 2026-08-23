FROM python:3.11-slim
WORKDIR /app
COPY platform/supply-chain/producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY platform/supply-chain/producer/produce_events.py .
COPY platform/supply-chain/schemas/supply_chain_event.avsc ./schemas/supply_chain_event.avsc
CMD ["python", "produce_events.py"]
