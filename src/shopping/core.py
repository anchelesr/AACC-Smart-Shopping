"""The parts of the application that publish and consume events (FR-19), on SQLite for the demonstration.

The database is the source of truth. Events only make reactions faster: a lost or duplicated event is
repaired by reconcile() (jobs) and by the cached pull in ModeReader (mode).
"""
from __future__ import annotations

import sqlite3
import time
from typing import Callable, Iterable

from events.bus import BusUnavailable, EventBus
from events.consumer import Metrics
from events.model import Event, MODE_KEY, TOPIC_MODE, TOPIC_PRICE

PULL_SECONDS = 60


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """SQLite connection with the full schema (shopping/schema.py)."""
    from .db import open_database
    return open_database("sqlite://" + path)


class PriceImporter:
    """Validate, upsert idempotently, then publish price.changed once per laptop that got new rows."""

    def __init__(self, db: sqlite3.Connection, bus: EventBus, metrics: Metrics) -> None:
        self.db, self.bus, self.metrics = db, bus, metrics

    def import_batch(self, batch_id: str, rows: Iterable[tuple[str, str, str, float]]) -> dict:
        new_per_laptop: dict[str, int] = {}
        rejected = 0
        for laptop, retailer, observed_at, price in rows:
            if not laptop or not retailer or not observed_at or price is None or price <= 0:
                rejected += 1
                continue
            cur = self.db.execute("INSERT OR IGNORE INTO observations (laptop_id, retailer, observed_at, price) VALUES (?, ?, ?, ?)", (laptop, retailer, observed_at, price))
            if cur.rowcount:
                new_per_laptop[laptop] = new_per_laptop.get(laptop, 0) + 1
        self.db.commit()                                   # state first, then the notification
        published = failed = 0
        for laptop, n in new_per_laptop.items():
            try:
                self.bus.publish(TOPIC_PRICE, Event.new(TOPIC_PRICE, laptop, {"laptop_id": laptop, "batch_id": batch_id, "new_observations": n}))
                published += 1
            except BusUnavailable:                         # the import must not fail because the bus is down
                failed += 1
                self.metrics["publish_failed"] += 1
        return {"accepted": sum(new_per_laptop.values()), "rejected": rejected, "published": published, "publish_failed": failed}


class JobScheduler:
    def __init__(self, db: sqlite3.Connection) -> None:
        self.db = db

    def enqueue_or_keep(self, laptop_id: str) -> bool:
        cur = self.db.execute("INSERT OR IGNORE INTO forecast_jobs (laptop_id, status, created_at) VALUES (?, 'queued', datetime('now'))", (laptop_id,))
        self.db.commit()
        return bool(cur.rowcount)

    def on_price_changed(self, event: Event) -> None:     # idempotent: at most one open job per laptop
        self.enqueue_or_keep(event.data["laptop_id"])

    def reconcile(self) -> int:
        """The pull path: create a job for every laptop whose newest observation is newer than its
        newest forecast and that has no open job. Repairs lost events."""
        rows = self.db.execute("""
            SELECT o.laptop_id FROM observations o
            GROUP BY o.laptop_id
            HAVING MAX(o.observed_at) > COALESCE((SELECT MAX(generated_at) FROM forecast_runs f WHERE f.laptop_id = o.laptop_id), '')
        """).fetchall()
        return sum(self.enqueue_or_keep(r[0]) for r in rows)

    def open_jobs(self) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT laptop_id FROM forecast_jobs WHERE status IN ('queued','running') ORDER BY laptop_id")]


class PolicyEngine:
    def __init__(self, db: sqlite3.Connection, bus: EventBus, metrics: Metrics) -> None:
        self.db, self.bus, self.metrics = db, bus, metrics

    def decide(self, mode: str, reason: str, placement_target: str, since: str) -> bool:
        """Store the decision; publish mode.changed only when the mode or the target changed."""
        cur_mode, cur_target, version = self.db.execute("SELECT mode, placement_target, policy_version FROM operating_mode_state WHERE id=1").fetchone()
        if (mode, placement_target) == (cur_mode, cur_target):
            return False
        self.db.execute("UPDATE operating_mode_state SET mode=?, reason=?, since=?, placement_target=? WHERE id=1", (mode, reason, since, placement_target))
        self.db.commit()
        try:
            self.bus.publish(TOPIC_MODE, Event.new(TOPIC_MODE, MODE_KEY, {"mode": mode, "reason": reason, "since": since, "placement_target": placement_target, "policy_version": version}))
        except BusUnavailable:
            self.metrics["publish_failed"] += 1
        return True


class ModeReader:
    """IOperatingMode.current(): pull with a cache of up to 60 s; mode.changed only invalidates it earlier."""

    def __init__(self, db: sqlite3.Connection, clock: Callable[[], float] = time.monotonic, pull_seconds: float = PULL_SECONDS) -> None:
        self.db, self.clock, self.pull_seconds = db, clock, pull_seconds
        self._cached: tuple | None = None
        self._at = 0.0

    def current(self) -> tuple[str, str]:
        if self._cached is None or self.clock() - self._at >= self.pull_seconds:
            mode, target = self.db.execute("SELECT mode, placement_target FROM operating_mode_state WHERE id=1").fetchone()
            self._cached, self._at = (mode, target), self.clock()
        return self._cached

    def on_mode_changed(self, event: Event) -> None:
        self._cached = None
