FROM flink:1.20.1-scala_2.12-java17
USER root
RUN apt-get update && apt-get install -y python3 python3-pip python3-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY flink-app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY flink-app/healthcare_graph_rag_job.py /app/healthcare_graph_rag_job.py
USER flink
