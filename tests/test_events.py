"""Tests for the event bus behaviour required by FR-19 and NFR-19. They run without a broker."""
import pytest

from events.bus import BusUnavailable, InMemoryBus, TOPIC_CONFIG, consumer_config, producer_config
from events.consumer import Metrics, ProcessedStore, drain, process_one
from events.model import Event, InvalidEvent, MODE_KEY, TOPIC_DEAD, TOPIC_MODE, TOPIC_PRICE
from shopping.core import JobScheduler, ModeReader, PolicyEngine, PriceImporter, connect

ROWS = [("laptop-1", "shop-a", "2026-11-25T08:00", 999.0), ("laptop-2", "shop-a", "2026-11-25T08:00", 1299.0)]


def price_event(laptop="laptop-1"):
    return Event.new(TOPIC_PRICE, laptop, {"laptop_id": laptop, "batch_id": "b1", "new_observations": 1})


def mode_event(mode="AMBER", target="eco"):
    return Event.new(TOPIC_MODE, MODE_KEY, {"mode": mode, "reason": "t", "since": "2026-11-25T09:00:00+00:00", "placement_target": target, "policy_version": 1})


@pytest.fixture
def env():
    bus, db = InMemoryBus(), connect()
    return bus, db, Metrics(), ProcessedStore()


# ---- schema
def test_event_roundtrip():
    ev = price_event()
    assert Event.from_bytes(ev.to_bytes()) == ev


@pytest.mark.parametrize("bad", [
    lambda: Event.new(TOPIC_PRICE, "l", {"laptop_id": "l", "batch_id": "b"}),                      # missing field
    lambda: Event.new(TOPIC_PRICE, "l", {"laptop_id": "l", "batch_id": "b", "new_observations": 0}),
    lambda: Event.new(TOPIC_MODE, MODE_KEY, {"mode": "BLUE", "reason": "r", "since": "s", "placement_target": "eco", "policy_version": 1}),
    lambda: Event.new("other.topic", "k", {}),
])
def test_invalid_events_are_rejected(bad):
    with pytest.raises(InvalidEvent):
        bad()


def test_unparsable_payload_is_rejected():
    with pytest.raises(InvalidEvent):
        Event.from_bytes(b"not json")


# ---- bus semantics
def test_same_key_stays_in_one_partition_and_in_order():
    bus = InMemoryBus()
    for i in range(5):
        bus.publish(TOPIC_PRICE, Event.new(TOPIC_PRICE, "laptop-1", {"laptop_id": "laptop-1", "batch_id": f"b{i}", "new_observations": 1}))
    sizes = [len(p) for p in bus.partitions[TOPIC_PRICE]]
    assert sorted(sizes) == [0, 0, 5]
    c = bus.subscribe(TOPIC_PRICE, "g")
    batches = [c.poll().event.data["batch_id"] for _ in range(5)]
    assert batches == ["b0", "b1", "b2", "b3", "b4"]


def test_each_consumer_group_gets_every_event(env):
    bus, *_ = env
    bus.publish(TOPIC_MODE, mode_event())
    got = {}
    for g in ("job-scheduler", "llm-gateway", "placement-controller"):
        got[g] = bus.subscribe(TOPIC_MODE, g).poll().event.data["mode"]
    assert got == {"job-scheduler": "AMBER", "llm-gateway": "AMBER", "placement-controller": "AMBER"}


def test_uncommitted_event_is_redelivered_after_a_crash():
    bus = InMemoryBus()
    bus.publish(TOPIC_MODE, mode_event())
    first = bus.subscribe(TOPIC_MODE, "g")
    assert first.poll() is not None           # received, then the consumer crashes before commit
    first.close()
    second = bus.subscribe(TOPIC_MODE, "g")
    assert second.poll() is not None


def test_lag_counts_uncommitted_events():
    bus = InMemoryBus()
    for _ in range(3):
        bus.publish(TOPIC_MODE, mode_event())
    c = bus.subscribe(TOPIC_MODE, "g")
    assert c.lag() == 3
    c.commit(c.poll())
    assert c.lag() == 2


# ---- FR-19 / NFR-19: the cases of the verification plan
def test_import_publishes_once_per_laptop_and_is_idempotent(env):
    bus, db, metrics, _ = env
    imp = PriceImporter(db, bus, metrics)
    assert imp.import_batch("b1", ROWS)["published"] == 2
    assert imp.import_batch("b1", ROWS) == {"accepted": 0, "rejected": 0, "published": 0, "publish_failed": 0}


def test_duplicated_price_event_creates_one_job(env):
    bus, db, metrics, store = env
    bus.duplicate_next = 2                                    # the producer delivers both events twice
    PriceImporter(db, bus, metrics).import_batch("b1", ROWS)
    sched = JobScheduler(db)
    drain(bus.subscribe(TOPIC_PRICE, "job-scheduler"), "job-scheduler", sched.on_price_changed, store, bus, metrics)
    assert sched.open_jobs() == ["laptop-1", "laptop-2"]
    assert metrics["duplicate"] == 2 and metrics["handled"] == 2


def test_handler_is_idempotent_even_without_the_processed_table(env):
    _, db, *_ = env
    sched = JobScheduler(db)
    sched.on_price_changed(price_event())
    sched.on_price_changed(price_event())                     # a different event id for the same laptop
    assert sched.open_jobs() == ["laptop-1"]


def test_lost_price_event_is_repaired_by_the_pull(env):
    bus, db, metrics, store = env
    bus.drop_next = 2                                         # both events are lost
    PriceImporter(db, bus, metrics).import_batch("b1", ROWS)
    sched = JobScheduler(db)
    drain(bus.subscribe(TOPIC_PRICE, "job-scheduler"), "job-scheduler", sched.on_price_changed, store, bus, metrics)
    assert sched.open_jobs() == []
    assert sched.reconcile() == 2
    assert sched.reconcile() == 0                             # nothing more to repair
    assert sched.open_jobs() == ["laptop-1", "laptop-2"]


def test_broker_down_does_not_fail_the_import_and_the_pull_repairs_it(env):
    bus, db, metrics, _ = env
    bus.down = True
    result = PriceImporter(db, bus, metrics).import_batch("b1", ROWS)
    assert result["accepted"] == 2 and result["publish_failed"] == 2 and metrics["publish_failed"] == 2
    assert JobScheduler(db).reconcile() == 2                  # shopper path and data are intact


def test_mode_changes_are_published_only_when_the_decision_changes(env):
    bus, db, metrics, _ = env
    pol = PolicyEngine(db, bus, metrics)
    assert pol.decide("AMBER", "carbon", "eco", "t1") is True
    assert pol.decide("AMBER", "carbon again", "eco", "t2") is False
    assert pol.decide("RED", "price", "eco", "t3") is True
    assert bus.subscribe(TOPIC_MODE, "g").lag() == 2


def test_mode_cache_is_at_most_60_seconds_old_and_events_invalidate_it(env):
    bus, db, metrics, _ = env
    now = [0.0]
    reader = ModeReader(db, clock=lambda: now[0])
    assert reader.current() == ("GREEN", "standard")
    PolicyEngine(db, InMemoryBus(), metrics).decide("RED", "price", "eco", "t")
    assert reader.current() == ("GREEN", "standard")          # still cached
    reader.on_mode_changed(mode_event())                      # the event makes the change visible at once
    assert reader.current() == ("RED", "eco")
    PolicyEngine(db, InMemoryBus(), metrics).decide("GREEN", "ok", "standard", "t2")
    now[0] = 61.0                                             # without an event the pull catches up
    assert reader.current() == ("GREEN", "standard")


# ---- retry and dead letter
def test_failing_handler_is_retried_then_dead_lettered(env):
    bus, _, metrics, store = env
    bus.publish(TOPIC_PRICE, price_event())
    calls = []

    def broken(ev):
        calls.append(ev.id)
        raise RuntimeError("boom")

    c = bus.subscribe(TOPIC_PRICE, "job-scheduler")
    assert process_one(c, "job-scheduler", broken, store, bus, metrics, max_attempts=3)
    assert len(calls) == 3 and metrics["dead"] == 1
    assert sum(len(p) for p in bus.partitions[TOPIC_DEAD]) == 1
    assert c.lag() == 0                                        # the partition is not blocked


def test_poison_message_is_dead_lettered_not_retried(env):
    bus, _, metrics, store = env
    bus.publish_raw(TOPIC_PRICE, "laptop-1", b"garbage")
    c = bus.subscribe(TOPIC_PRICE, "job-scheduler")
    assert process_one(c, "job-scheduler", lambda e: None, store, bus, metrics)
    assert metrics["dead"] == 1 and metrics["handled"] == 0


def test_a_transient_failure_succeeds_on_retry(env):
    bus, _, metrics, store = env
    bus.publish(TOPIC_PRICE, price_event())
    attempts = []

    def flaky(ev):
        attempts.append(1)
        if len(attempts) < 2:
            raise RuntimeError("temporary")

    process_one(bus.subscribe(TOPIC_PRICE, "g"), "g", flaky, store, bus, metrics)
    assert metrics["handled"] == 1 and metrics["retried"] == 1 and metrics["dead"] == 0


# ---- Kafka settings (checked without a broker)
def test_producer_waits_for_all_replicas_and_is_idempotent():
    cfg = producer_config("kafka:9092")
    assert cfg["acks"] == "all" and cfg["enable.idempotence"] is True


def test_consumer_commits_manually_and_reads_new_groups_from_the_start():
    cfg = consumer_config("kafka:9092", "job-scheduler")
    assert cfg["enable.auto.commit"] is False and cfg["auto.offset.reset"] == "earliest" and cfg["group.id"] == "job-scheduler"


def test_topic_layout():
    assert TOPIC_CONFIG[TOPIC_MODE]["partitions"] == 1          # strict order of mode changes
    assert TOPIC_CONFIG[TOPIC_PRICE]["partitions"] >= 3         # scheduler replicas can share the load
