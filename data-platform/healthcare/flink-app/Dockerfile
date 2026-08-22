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
WORKDIR /app
COPY data-platform/healthcare/flink-app/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt
COPY data-platform/healthcare/flink-app/app /app/app
COPY data-platform/healthcare/flink-app/healthcare_graph_rag_job.py /app/healthcare_graph_rag_job.py
COPY data-platform/healthcare/flink-app/healthcare_graph_rag_pyflink_job.py /app/healthcare_graph_rag_pyflink_job.py
COPY data-platform/healthcare/ontology /app/config/ontology
COPY data-platform/shared /app/shared_lib
USER flink
