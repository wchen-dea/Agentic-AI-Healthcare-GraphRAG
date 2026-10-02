FROM python:3.11-slim
WORKDIR /app
COPY domains/healthcare/data-pipelines/producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY domains/healthcare/data-pipelines/producer/produce_events.py .
COPY domains/healthcare/data-pipelines/schemas/medical_event.avsc ./schemas/medical_event.avsc
CMD ["python", "produce_events.py"]
