FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY mcp-server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY mcp-server/app ./app
COPY mcp-server/config ./config
RUN mkdir -p /app/logs

CMD ["python", "-m", "app.server"]
