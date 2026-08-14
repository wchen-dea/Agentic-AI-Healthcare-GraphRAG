FROM python:3.11-slim
WORKDIR /app
COPY domains/supply-chain/producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/supply-chain/producer/produce_events.py .
COPY domains/supply-chain/schemas/supply_chain_event.avsc ./schemas/supply_chain_event.avsc
CMD ["python", "produce_events.py"]
