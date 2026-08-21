"""Native PyFlink DataStream job for Supply Chain GraphRAG processing.

Mirrors the healthcare PyFlink pattern: one KafkaSource per topic, a shared
processor for side-effect sinks (Qdrant + Neo4j), submitted to the shared
Flink cluster via flink run.
"""

import os

from pyflink.common import WatermarkStrategy
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common.typeinfo import Types
from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import KafkaOffsetsInitializer, KafkaSource
from pyflink.datastream.functions import MapFunction

from supplychain_graph_rag_job import (
    ALL_TOPICS,
    REFERENCE_TOPIC_SET,
    TOPIC_SET,
    SupplyChainProcessor,
)

KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.getenv("FLINK_KAFKA_GROUP_ID", "supplychain-graphrag-pyflink")
CHECKPOINT_INTERVAL_MS = int(os.getenv("FLINK_CHECKPOINT_INTERVAL_MS", "10000"))
PARALLELISM = int(os.getenv("FLINK_JOB_PARALLELISM", "1"))


class SupplyChainSideEffectMap(MapFunction):
    _shared_processor = None

    def __init__(self, topic):
        self.topic = topic

    def _get_processor(self):
        if SupplyChainSideEffectMap._shared_processor is None:
            SupplyChainSideEffectMap._shared_processor = SupplyChainProcessor()
        return SupplyChainSideEffectMap._shared_processor

    def map(self, value):
        processor = self._get_processor()
        raw = value.encode("ISO-8859-1") if isinstance(value, str) else value
        try:
            result = processor.handle_topic_message(self.topic, raw)
            return result
        except Exception as ex:
            return f"error:{self.topic}:{ex}"


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
            SupplyChainSideEffectMap(topic),
            output_type=Types.STRING(),
        )
        streams.append(processed)

    if not streams:
        raise RuntimeError("No topics configured for PyFlink consumer")

    merged = streams[0]
    for s in streams[1:]:
        merged = merged.union(s)

    merged.print()
    env.execute("SupplyChainGraphRagPyFlinkJob")


if __name__ == "__main__":
    main()
