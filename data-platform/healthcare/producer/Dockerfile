FROM python:3.11-slim
WORKDIR /app
COPY data-platform/healthcare/producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY data-platform/healthcare/producer/produce_events.py .
COPY data-platform/healthcare/schemas/medical_event.avsc ./schemas/medical_event.avsc
CMD ["python", "produce_events.py"]
