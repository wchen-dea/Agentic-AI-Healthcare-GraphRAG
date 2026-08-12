from __future__ import annotations

import time
from typing import Any


def run_consumer_loop(
    consumer,
    processor,
    *,
    kafka_exception_cls=Exception,
    poll_timeout_seconds: float = 1.0,
    failure_sleep_seconds: float = 1.0,
) -> None:
    """Run the poll/process/commit loop for the streaming processor."""
    while True:
        msg = consumer.poll(poll_timeout_seconds)
        if msg is None:
            continue
        if msg.error():
            raise kafka_exception_cls(msg.error())
        try:
            topic = msg.topic()
            raw = msg.value()
            processor.handle_topic_message(topic, raw)
            consumer.commit(msg, asynchronous=False)
        except Exception as ex:
            print(f"FAILED processing key={msg.key()} error={ex}")
            time.sleep(failure_sleep_seconds)
