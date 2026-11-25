"""End-to-end demonstration: import prices, change the mode, let three consumer groups react.

    python -m events.demo                     # in-memory bus
    KAFKA_BOOTSTRAP=localhost:9092 python -m events.demo   # real Kafka (docker compose up -d)
"""
from __future__ import annotations

import os
import time

from events.bus import InMemoryBus, KafkaBus, ensure_topics
from events.consumer import Metrics, ProcessedStore, drain
from events.model import TOPIC_MODE, TOPIC_PRICE
from shopping.core import JobScheduler, ModeReader, PolicyEngine, PriceImporter, connect


def main() -> None:
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP")
    if bootstrap:
        ensure_topics(bootstrap)
        bus = KafkaBus(bootstrap)
        suffix = str(int(time.time()))                       # fresh consumer groups for a repeatable demo
    else:
        bus, suffix = InMemoryBus(), "demo"
    print("bus:", "Kafka " + bootstrap if bootstrap else "in memory")
    db, metrics, store = connect(), Metrics(), ProcessedStore()
    scheduler, reader = JobScheduler(db), ModeReader(db)

    result = PriceImporter(db, bus, metrics).import_batch("batch-1", [
        ("laptop-1", "shop-a", "2026-11-25T08:00", 999.0), ("laptop-1", "shop-b", "2026-11-25T08:00", 1019.0),
        ("laptop-2", "shop-a", "2026-11-25T08:00", 1299.0), ("laptop-2", "shop-a", "2026-11-25T08:00", 1299.0)])
    print("import:", result)

    sched_c = bus.subscribe(TOPIC_PRICE, f"job-scheduler-{suffix}")
    deadline = time.time() + 20
    while len(scheduler.open_jobs()) < 2 and time.time() < deadline:
        drain(sched_c, f"job-scheduler-{suffix}", scheduler.on_price_changed, store, bus, metrics)
        time.sleep(0.2)
    print("open jobs after price.changed:", scheduler.open_jobs())

    print("mode before the decision (cached):", reader.current())
    changed = PolicyEngine(db, bus, metrics).decide("AMBER", "carbon_intensity=340", "eco", "2026-11-25T09:00:00+00:00")
    print("mode decision published:", changed, "| mode still served from the cache:", reader.current())
    seen = {}
    for group in ("job-scheduler", "llm-gateway", "placement-controller"):
        c = bus.subscribe(TOPIC_MODE, f"{group}-{suffix}")
        deadline = time.time() + 20
        while time.time() < deadline:
            d = c.poll(0.5)
            if d and d.event:
                seen[group] = d.event.data["mode"]
                c.commit(d)
                break
        c.close()
    reader.on_mode_changed(None)
    print("each group received mode.changed:", seen, "| mode after invalidation:", reader.current())
    print("metrics:", dict(metrics))


if __name__ == "__main__":
    main()
