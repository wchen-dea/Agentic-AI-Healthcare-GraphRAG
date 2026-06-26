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
    def __init__(self):
        self.processor = None

    def map(self, value):
        if self.processor is None:
            self.processor = HealthcareGraphRagProcessor()

        topic, raw = value
        if topic in REFERENCE_TOPICS:
            self.processor.process_reference_event(topic, raw)
            return f"reference:{topic}"
        if topic in TOPICS:
            self.processor.process_event(raw)
            return f"event:{topic}"
        return f"skipped:{topic}"


def main():
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(PARALLELISM)
    env.enable_checkpointing(CHECKPOINT_INTERVAL_MS)

    streams = []
    for topic in ALL_TOPICS:
        source = KafkaSource.builder() \
            .set_bootstrap_servers(KAFKA_BOOTSTRAP) \
            .set_group_id(f"{GROUP_ID}-{topic.replace('.', '-')}") \
            .set_topics(topic) \
            .set_starting_offsets(KafkaOffsetsInitializer.earliest()) \
            .set_value_only_deserializer(SimpleStringSchema()) \
            .build()

        tagged = env.from_source(
            source,
            WatermarkStrategy.no_watermarks(),
            f"kafka-source-{topic}",
        ).map(
            lambda raw, topic_name=topic: (topic_name, raw),
            output_type=Types.TUPLE([Types.STRING(), Types.STRING()]),
        )
        streams.append(tagged)

    if not streams:
        raise RuntimeError("No topics configured for PyFlink consumer")

    stream = streams[0]
    for tagged_stream in streams[1:]:
        stream = stream.union(tagged_stream)

    processed = stream.map(
        GraphRagSideEffectMap(), output_type=Types.STRING()
    )

    processed.print()
    env.execute("HealthcareGraphRagPyFlinkJob")


if __name__ == "__main__":
    main()
