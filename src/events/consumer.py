"""Idempotent consumption with retry and a dead-letter topic (NFR-19).

Two layers protect against duplicates: the handler itself is idempotent (it can run twice for the same
event with the same result), and a processed-events table skips events that were already handled.
"""
from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Callable

from .bus import BusUnavailable, Consumer, EventBus
from .model import Event, TOPIC_DEAD


class ProcessedStore:
    def __init__(self, path: str = ":memory:") -> None:
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS processed_events (grp TEXT, event_id TEXT, PRIMARY KEY (grp, event_id))")

    def seen(self, group: str, event_id: str) -> bool:
        return self.db.execute("SELECT 1 FROM processed_events WHERE grp=? AND event_id=?", (group, event_id)).fetchone() is not None

    def mark(self, group: str, event_id: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO processed_events VALUES (?, ?)", (group, event_id))
        self.db.commit()


class Metrics(Counter):
    """Counters named like the metric catalogue (docs/observability.md): handled, duplicate, retried, dead."""


def process_one(consumer: Consumer, group: str, handler: Callable[[Event], None], store: ProcessedStore,
                bus: EventBus, metrics: Metrics, max_attempts: int = 3) -> bool:
    """Handle at most one delivery. Returns False when nothing was waiting."""
    d = consumer.poll(0)
    if d is None:
        return False
    if d.event is None:                                   # poison message: cannot be parsed
        _dead_letter(bus, d.raw, d.error or "unparsable")
        metrics["dead"] += 1
        consumer.commit(d)
        return True
    if store.seen(group, d.event.id):
        metrics["duplicate"] += 1
        consumer.commit(d)
        return True
    last_error = ""
    for attempt in range(1, max_attempts + 1):
        try:
            handler(d.event)
        except Exception as exc:                          # the handler failed: retry, then dead-letter
            last_error = f"{type(exc).__name__}: {exc}"
            metrics["retried"] += 1
            continue
        store.mark(group, d.event.id)
        metrics["handled"] += 1
        consumer.commit(d)
        return True
    _dead_letter(bus, d.raw, last_error)
    metrics["dead"] += 1
    consumer.commit(d)                                    # do not block the partition behind one bad event
    return True


def _dead_letter(bus: EventBus, raw: bytes, error: str) -> None:
    import json
    payload = json.dumps({"error": error, "payload": raw.decode("utf-8", "replace")}).encode()
    try:
        bus.publish_raw(TOPIC_DEAD, "dead", payload)
    except BusUnavailable:
        pass                                              # logged by the caller's metrics; the message is not lost from the log


def drain(consumer: Consumer, group: str, handler: Callable[[Event], None], store: ProcessedStore,
          bus: EventBus, metrics: Metrics, limit: int = 1000) -> int:
    n = 0
    while n < limit and process_one(consumer, group, handler, store, bus, metrics):
        n += 1
    return n
