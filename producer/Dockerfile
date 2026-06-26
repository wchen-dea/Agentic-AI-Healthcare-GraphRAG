FROM python:3.11-slim
WORKDIR /app
COPY producer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY producer/produce_events.py .
COPY schemas/medical_event.avsc ./schemas/medical_event.avsc
CMD ["python", "produce_events.py"]
