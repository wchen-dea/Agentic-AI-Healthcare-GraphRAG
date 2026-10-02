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
	&& pip3 install --no-cache-dir apache-flink==1.20.5 confluent-kafka==2.5.3 fastavro==1.9.7 neo4j==5.24.0 qdrant-client==1.11.3 requests==2.32.3 PyYAML==6.0.2 \
	&& rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=knowledge-core-wheel /wheels /tmp/wheels
RUN pip3 install --no-cache-dir /tmp/wheels/knowledge_core-*.whl && rm -rf /tmp/wheels
USER flink
