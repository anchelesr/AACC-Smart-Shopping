"""The Kafka adapter against a fake client library: checks how we call confluent-kafka, without a broker."""
import sys
import types

import pytest

from events.bus import BusUnavailable
from events.model import Event, MODE_KEY, TOPIC_MODE


class FakeMsg:
    def __init__(self, topic, partition, offset, value):
        self._t, self._p, self._o, self._v = topic, partition, offset, value
    def topic(self): return self._t
    def partition(self): return self._p
    def offset(self): return self._o
    def value(self): return self._v
    def error(self): return None


class FakeProducer:
    fail = False
    def __init__(self, cfg): self.cfg, self.sent = cfg, []
    def produce(self, topic, key, value, on_delivery):
        self.sent.append((topic, key, value))
        on_delivery("broker unreachable" if FakeProducer.fail else None, None)
    def flush(self, timeout): return 0


class FakeConsumer:
    def __init__(self, cfg): self.cfg, self.commits, self.queue = cfg, [], []
    def subscribe(self, topics): self.topics = topics
    def poll(self, timeout): return self.queue.pop(0) if self.queue else None
    def commit(self, offsets, asynchronous): self.commits.append((offsets, asynchronous))
    def close(self): pass


@pytest.fixture
def kafka(monkeypatch):
    mod = types.ModuleType("confluent_kafka")
    mod.Producer, mod.Consumer = FakeProducer, FakeConsumer
    mod.TopicPartition = lambda t, p, o: (t, p, o)
    monkeypatch.setitem(sys.modules, "confluent_kafka", mod)
    FakeProducer.fail = False
    from events.bus import KafkaBus
    return KafkaBus("kafka:9092")


def ev():
    return Event.new(TOPIC_MODE, MODE_KEY, {"mode": "RED", "reason": "r", "since": "s", "placement_target": "eco", "policy_version": 1})


def test_publish_uses_the_event_key_and_json_payload(kafka):
    e = ev()
    kafka.publish(TOPIC_MODE, e)
    topic, key, value = kafka._producer.sent[0]
    assert topic == TOPIC_MODE and key == MODE_KEY.encode() and Event.from_bytes(value) == e
    assert kafka._producer.cfg["acks"] == "all"


def test_unacknowledged_publish_raises_bus_unavailable(kafka):
    FakeProducer.fail = True
    with pytest.raises(BusUnavailable):
        kafka.publish(TOPIC_MODE, ev())


def test_consumer_commits_offset_plus_one_synchronously(kafka):
    c = kafka.subscribe(TOPIC_MODE, "g")
    c._c.queue.append(FakeMsg(TOPIC_MODE, 0, 41, ev().to_bytes()))
    d = c.poll(0)
    assert d.event is not None and d.offset == 41
    c.commit(d)
    assert c._c.commits == [([(TOPIC_MODE, 0, 42)], False)]
    assert c._c.cfg["enable.auto.commit"] is False


def test_unparsable_message_becomes_a_delivery_without_event(kafka):
    c = kafka.subscribe(TOPIC_MODE, "g")
    c._c.queue.append(FakeMsg(TOPIC_MODE, 0, 1, b"garbage"))
    d = c.poll(0)
    assert d.event is None and d.raw == b"garbage" and d.error
