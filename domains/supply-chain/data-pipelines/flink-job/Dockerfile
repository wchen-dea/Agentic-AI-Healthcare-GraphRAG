FROM ghcr.io/astral-sh/uv:0.12.11 AS uv

FROM python:3.11-slim AS knowledge-core-wheel
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /src
COPY packages/knowledge-core /src/packages/knowledge-core
RUN uv build --wheel --out-dir /wheels packages/knowledge-core

FROM flink:1.20.5-scala_2.12-java17
USER root
RUN apt-get update && apt-get install -y python3 python3-pip python3-dev default-jdk-headless curl \
	&& ln -sf /usr/bin/python3 /usr/bin/python \
	&& mkdir -p /opt/java/openjdk \
	&& ln -sf "$(dirname "$(dirname "$(readlink -f "$(which javac)")")")/include" /opt/java/openjdk/include \
	&& curl -fsSL -o /opt/flink/lib/flink-connector-kafka-3.4.0-1.20.jar \
	  https://repo1.maven.org/maven2/org/apache/flink/flink-connector-kafka/3.4.0-1.20/flink-connector-kafka-3.4.0-1.20.jar \
	&& curl -fsSL -o /opt/flink/lib/kafka-clients-3.7.1.jar \
	  https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.7.1/kafka-clients-3.7.1.jar \
	&& rm -rf /var/lib/apt/lists/*
# Ingest must embed with the same model the agent service uses for queries
# (see docs: "Embedding parity"). EMBEDDING_REQUIRE_MODEL fails fast instead of
# silently writing incompatible MD5 hash vectors to Qdrant.
ARG EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EMBEDDING_MODEL=${EMBEDDING_MODEL} \
	EMBEDDING_REQUIRE_MODEL=true \
	HF_HOME=/opt/hf-cache \
	SENTENCE_TRANSFORMERS_HOME=/opt/hf-cache
WORKDIR /app
RUN pip3 install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY domains/supply-chain/data-pipelines/flink-job/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY domains/supply-chain/data-pipelines/flink-job/app /app/app
COPY domains/supply-chain/data-pipelines/flink-job/supplychain_graph_rag_job.py /app/supplychain_graph_rag_job.py
COPY domains/supply-chain/data-pipelines/flink-job/supplychain_graph_rag_pyflink_job.py /app/supplychain_graph_rag_pyflink_job.py
COPY --from=knowledge-core-wheel /wheels /tmp/wheels
RUN pip3 install --no-cache-dir /tmp/wheels/knowledge_core-*.whl && rm -rf /tmp/wheels
RUN python3 -c "import os; from sentence_transformers import SentenceTransformer; SentenceTransformer(os.environ['EMBEDDING_MODEL'])" \
	&& chown -R flink:flink /opt/hf-cache
USER flink
