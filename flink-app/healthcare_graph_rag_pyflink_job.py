"""
Native PyFlink DataStream job for Healthcare GraphRAG processing.

This job consumes all healthcare topics using a custom Kafka source and reuses the
existing HealthcareGraphRagProcessor side-effect sinks for Qdrant and Neo4j.
"""

import os

from pyflink.common import WatermarkStrategy
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource
from pyflink.datastream.functions import MapFunction

from healthcare_graph_rag_job import (
    ALL_TOPICS,
    REFERENCE_TOPICS,
    TOPICS,
    HealthcareGraphRagProcessor,
)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.getenv("FLINK_KAFKA_GROUP_ID", "healthcare-graphrag-pyflink")
CHECKPOINT_INTERVAL_MS = int(os.getenv("FLINK_CHECKPOINT_INTERVAL_MS", "10000"))
PARALLELISM = int(os.getenv("FLINK_JOB_PARALLELISM", "1"))


class GraphRagSideEffectMap(MapFunction):
    def __init__(self, topic):
        self.topic = topic
        self.processor = None

    def map(self, value):
        if self.processor is None:
            self.processor = HealthcareGraphRagProcessor()

        # Preserve exact byte values from Kafka by round-tripping through ISO-8859-1.
        raw = value.encode("ISO-8859-1") if isinstance(value, str) else value

        if self.topic in REFERENCE_TOPICS:
            self.processor.process_reference_event(self.topic, raw)
            return f"reference:{self.topic}"
        if self.topic in TOPICS:
            self.processor.process_event(raw, self.topic)
            return f"event:{self.topic}"
        return f"skipped:{self.topic}"


def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(PARALLELISM)
    env.enable_checkpointing(CHECKPOINT_INTERVAL_MS)

    streams = []
    deserializer = SimpleStringSchema("ISO-8859-1")
    for topic in ALL_TOPICS:
        source = KafkaSource.builder() \
            .set_bootstrap_servers(KAFKA_BOOTSTRAP) \
            .set_group_id(f"{GROUP_ID}-{topic.replace('.', '-')}") \
            .set_topics(topic) \
            .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
            .set_value_only_deserializer(deserializer) \
            .build()

        processed = env.from_source(
            source,
            WatermarkStrategy.no_watermarks(),
            f"kafka-source-{topic}",
        ).map(
            GraphRagSideEffectMap(topic),
            output_type=Types.STRING(),
        )
        streams.append(processed)

    if not streams:
        raise RuntimeError("No topics configured for PyFlink consumer")

    merged = streams[0]
    for output_stream in streams[1:]:
        merged = merged.union(output_stream)

    merged.print()
    env.execute("HealthcareGraphRagPyFlinkJob")


if __name__ == "__main__":
    main()
