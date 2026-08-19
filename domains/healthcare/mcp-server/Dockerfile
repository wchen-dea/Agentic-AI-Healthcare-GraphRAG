FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY domains/healthcare/mcp-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY domains/healthcare/mcp-server/app ./app
COPY domains/healthcare/mcp-server/config ./config
RUN mkdir -p /app/logs

CMD ["python", "-m", "app.server"]
