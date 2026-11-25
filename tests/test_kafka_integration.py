"""Round trip against a real broker. Skipped unless KAFKA_BOOTSTRAP is set (docker compose up -d, or the CI service)."""
import os
import time
import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.skipif(not os.environ.get("KAFKA_BOOTSTRAP"), reason="no Kafka broker configured")]

from events.bus import KafkaBus, ensure_topics
from events.consumer import Metrics, ProcessedStore, drain
from events.model import Event, MODE_KEY, TOPIC_MODE, TOPIC_PRICE
from shopping.core import JobScheduler, connect


@pytest.fixture(scope="module")
def bus():
    bootstrap = os.environ["KAFKA_BOOTSTRAP"]
    ensure_topics(bootstrap)
    ensure_topics(bootstrap)          # second call must be harmless (topics exist)
    return KafkaBus(bootstrap)


def wait_for(cond, seconds=30):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def test_price_event_reaches_the_scheduler_once_even_if_published_twice(bus):
    laptop = f"laptop-{uuid.uuid4().hex[:8]}"
    ev = Event.new(TOPIC_PRICE, laptop, {"laptop_id": laptop, "batch_id": "it", "new_observations": 1})
    bus.publish(TOPIC_PRICE, ev)
    bus.publish(TOPIC_PRICE, ev)                                  # same event id: a retry from the producer
    db, metrics, store = connect(), Metrics(), ProcessedStore()
    sched, group = JobScheduler(db), f"it-{uuid.uuid4().hex[:8]}"
    consumer = bus.subscribe(TOPIC_PRICE, group)
    assert wait_for(lambda: drain(consumer, group, sched.on_price_changed, store, bus, metrics) or laptop in sched.open_jobs())
    drain(consumer, group, sched.on_price_changed, store, bus, metrics)
    consumer.close()
    assert sched.open_jobs().count(laptop) == 1


def test_mode_event_is_delivered_to_every_group_with_its_content(bus):
    ev = Event.new(TOPIC_MODE, MODE_KEY, {"mode": "RED", "reason": "it", "since": "2026-11-25T09:00:00+00:00", "placement_target": "eco", "policy_version": 7})
    bus.publish(TOPIC_MODE, ev)
    for group in (f"a-{uuid.uuid4().hex[:6]}", f"b-{uuid.uuid4().hex[:6]}"):
        c = bus.subscribe(TOPIC_MODE, group)
        found = []
        assert wait_for(lambda: found.extend(filter(None, [c.poll(0.5)])) or any(d.event and d.event.id == ev.id for d in found))
        c.close()


def test_uncommitted_event_is_redelivered_to_the_same_group(bus):
    ev = Event.new(TOPIC_MODE, MODE_KEY, {"mode": "AMBER", "reason": "it", "since": "2026-11-25T09:00:00+00:00", "placement_target": "eco", "policy_version": 8})
    bus.publish(TOPIC_MODE, ev)
    group = f"redeliver-{uuid.uuid4().hex[:8]}"
    first = bus.subscribe(TOPIC_MODE, group)
    got = []
    assert wait_for(lambda: got.extend(filter(None, [first.poll(0.5)])) or any(d.event and d.event.id == ev.id for d in got))
    first.close()                                                 # closed without commit
    second = bus.subscribe(TOPIC_MODE, group)
    again = []
    assert wait_for(lambda: again.extend(filter(None, [second.poll(0.5)])) or any(d.event and d.event.id == ev.id for d in again))
    second.close()
