"""IEventBus: publish(topic, event) and subscribe(topic, group). Two implementations.

Delivery is at-least-once. A consumer commits its offset only after the handler succeeded, so a crash
between handling and commit redelivers the event; consumers are therefore idempotent (see consumer.py).
"""
from __future__ import annotations

import os
import zlib
from dataclasses import dataclass
from typing import Optional, Protocol

from .model import Event, InvalidEvent, TOPIC_MODE, TOPIC_PRICE, TOPIC_DEAD

# Topic layout (also used by deploy/kafka). Retention 7 days; replication 1 on the single demonstration broker.
TOPIC_CONFIG = {
    TOPIC_PRICE: {"partitions": 3, "retention_ms": 7 * 24 * 3600 * 1000},
    TOPIC_MODE: {"partitions": 1, "retention_ms": 7 * 24 * 3600 * 1000},
    TOPIC_DEAD: {"partitions": 1, "retention_ms": 14 * 24 * 3600 * 1000},
}


class BusUnavailable(Exception):
    """The broker could not be reached or did not acknowledge the message."""


@dataclass
class Delivery:
    topic: str
    partition: int
    offset: int
    event: Optional[Event]      # None when the payload could not be parsed
    raw: bytes
    error: str = ""


class Consumer(Protocol):
    def poll(self, timeout: float = 0.0) -> Optional[Delivery]: ...
    def commit(self, delivery: Delivery) -> None: ...
    def lag(self) -> int: ...
    def close(self) -> None: ...


class EventBus(Protocol):
    def publish(self, topic: str, event: Event) -> None: ...
    def publish_raw(self, topic: str, key: str, payload: bytes) -> None: ...
    def subscribe(self, topic: str, group: str) -> Consumer: ...


# ----------------------------------------------------------------------------- in memory (tests, demo)
class InMemoryBus:
    """Same semantics as the Kafka bus (partitions by key, consumer groups, commit after handling),
    plus fault injection so that the failure cases of NFR-19 can be tested without a broker."""

    def __init__(self) -> None:
        self.partitions: dict[str, list[list[bytes]]] = {}
        self.committed: dict[tuple[str, str, int], int] = {}
        self.down = False
        self.drop_next = 0
        self.duplicate_next = 0

    def _log(self, topic: str) -> list[list[bytes]]:
        if topic not in self.partitions:
            n = TOPIC_CONFIG.get(topic, {"partitions": 1})["partitions"]
            self.partitions[topic] = [[] for _ in range(n)]
        return self.partitions[topic]

    def publish(self, topic: str, event: Event) -> None:
        self.publish_raw(topic, event.key, event.to_bytes())

    def publish_raw(self, topic: str, key: str, payload: bytes) -> None:
        if self.down:
            raise BusUnavailable("broker down")
        if self.drop_next:
            self.drop_next -= 1
            return                                   # acknowledged but lost (injected fault)
        log = self._log(topic)
        part = zlib.crc32(key.encode()) % len(log)
        log[part].append(payload)
        if self.duplicate_next:
            self.duplicate_next -= 1
            log[part].append(payload)                # delivered twice (producer retry)

    def subscribe(self, topic: str, group: str) -> "_MemConsumer":
        return _MemConsumer(self, topic, group)


class _MemConsumer:
    def __init__(self, bus: InMemoryBus, topic: str, group: str) -> None:
        self.bus, self.topic, self.group = bus, topic, group
        self.position = {p: bus.committed.get((group, topic, p), 0) for p in range(len(bus._log(topic)))}

    def poll(self, timeout: float = 0.0) -> Optional[Delivery]:
        if self.bus.down:
            return None
        log = self.bus._log(self.topic)
        for p, msgs in enumerate(log):
            pos = self.position[p]
            if pos < len(msgs):
                self.position[p] = pos + 1
                raw = msgs[pos]
                try:
                    return Delivery(self.topic, p, pos, Event.from_bytes(raw), raw)
                except InvalidEvent as exc:
                    return Delivery(self.topic, p, pos, None, raw, str(exc))
        return None

    def commit(self, delivery: Delivery) -> None:
        self.bus.committed[(self.group, self.topic, delivery.partition)] = delivery.offset + 1

    def lag(self) -> int:
        log = self.bus._log(self.topic)
        return sum(len(m) - self.bus.committed.get((self.group, self.topic, p), 0) for p, m in enumerate(log))

    def close(self) -> None:          # uncommitted messages will be redelivered to the next consumer
        pass


# ----------------------------------------------------------------------------- Kafka
def producer_config(bootstrap: str) -> dict:
    """acks=all and idempotence: no loss on broker failover and no duplicates caused by producer retries."""
    return {"bootstrap.servers": bootstrap, "client.id": "smart-shopping-producer", "acks": "all",
            "enable.idempotence": True, "linger.ms": 5, "delivery.timeout.ms": 10000, "request.timeout.ms": 5000}


def consumer_config(bootstrap: str, group: str) -> dict:
    """Manual commit after the handler succeeded (at-least-once); a new group starts at the beginning."""
    return {"bootstrap.servers": bootstrap, "group.id": group, "enable.auto.commit": False,
            "auto.offset.reset": "earliest", "session.timeout.ms": 10000, "client.id": f"smart-shopping-{group}"}


class KafkaBus:
    def __init__(self, bootstrap: Optional[str] = None) -> None:
        from confluent_kafka import Producer          # imported here so tests without a broker need no client
        self.bootstrap = bootstrap or os.environ.get("KAFKA_BOOTSTRAP", "kafka:9092")
        self._producer = Producer(producer_config(self.bootstrap))

    def publish(self, topic: str, event: Event) -> None:
        self.publish_raw(topic, event.key, event.to_bytes())

    def publish_raw(self, topic: str, key: str, payload: bytes) -> None:
        errors: list = []
        try:
            self._producer.produce(topic, key=key.encode(), value=payload, on_delivery=lambda err, msg: errors.append(err) if err else None)
            remaining = self._producer.flush(10)
        except Exception as exc:                      # BufferError, KafkaException
            raise BusUnavailable(str(exc)) from exc
        if remaining or errors:
            raise BusUnavailable(f"not acknowledged: {errors[0] if errors else 'timeout'}")

    def subscribe(self, topic: str, group: str) -> "_KafkaConsumer":
        return _KafkaConsumer(self.bootstrap, topic, group)


class _KafkaConsumer:
    def __init__(self, bootstrap: str, topic: str, group: str) -> None:
        from confluent_kafka import Consumer as KConsumer
        self.topic = topic
        self._c = KConsumer(consumer_config(bootstrap, group))
        self._c.subscribe([topic])

    def poll(self, timeout: float = 0.0) -> Optional[Delivery]:
        msg = self._c.poll(timeout)
        if msg is None or msg.error():
            return None
        raw = msg.value() or b""
        try:
            return Delivery(msg.topic(), msg.partition(), msg.offset(), Event.from_bytes(raw), raw)
        except InvalidEvent as exc:
            return Delivery(msg.topic(), msg.partition(), msg.offset(), None, raw, str(exc))

    def commit(self, delivery: Delivery) -> None:
        from confluent_kafka import TopicPartition
        self._c.commit(offsets=[TopicPartition(delivery.topic, delivery.partition, delivery.offset + 1)], asynchronous=False)

    def lag(self) -> int:
        from confluent_kafka import TopicPartition
        total = 0
        for tp in self._c.committed(self._c.assignment(), timeout=5):
            _, high = self._c.get_watermark_offsets(tp, timeout=5)
            total += high - (tp.offset if tp.offset >= 0 else 0)
        return total

    def close(self) -> None:
        self._c.close()


def ensure_topics(bootstrap: str) -> None:
    """Create the topics if they do not exist (the Kubernetes Job and docker-compose do the same)."""
    from confluent_kafka.admin import AdminClient, NewTopic
    admin = AdminClient({"bootstrap.servers": bootstrap})
    futures = admin.create_topics([
        NewTopic(t, num_partitions=c["partitions"], replication_factor=1,
                 config={"retention.ms": str(c["retention_ms"]), "cleanup.policy": "delete"})
        for t, c in TOPIC_CONFIG.items()])
    for topic, fut in futures.items():
        try:
            fut.result(15)
        except Exception as exc:
            if "TOPIC_ALREADY_EXISTS" not in str(exc):
                raise
