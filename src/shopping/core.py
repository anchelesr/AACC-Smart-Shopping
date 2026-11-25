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
    db = sqlite3.connect(path)
    db.execute("PRAGMA foreign_keys = ON")
    db.executescript("""
    CREATE TABLE IF NOT EXISTS observations (laptop_id TEXT, retailer TEXT, observed_at TEXT, price REAL,
                                             PRIMARY KEY (laptop_id, retailer, observed_at));
    CREATE TABLE IF NOT EXISTS products (laptop_id TEXT PRIMARY KEY, brand TEXT, model TEXT);
    CREATE TABLE IF NOT EXISTS watches (id INTEGER PRIMARY KEY AUTOINCREMENT, device_id TEXT NOT NULL, laptop_id TEXT NOT NULL,
                                        target_price REAL NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
                                        alerted INTEGER NOT NULL DEFAULT 0, episode INTEGER NOT NULL DEFAULT 0,
                                        created_at TEXT NOT NULL DEFAULT (datetime('now')), UNIQUE (device_id, laptop_id));
    CREATE TABLE IF NOT EXISTS alerts (id INTEGER PRIMARY KEY AUTOINCREMENT, watch_id INTEGER NOT NULL REFERENCES watches(id) ON DELETE CASCADE,
                                       price REAL, retailer TEXT, observed_at TEXT, dedup_key TEXT NOT NULL UNIQUE,
                                       created_at TEXT NOT NULL DEFAULT (datetime('now')), read_at TEXT);
    CREATE TABLE IF NOT EXISTS watch_checks (id INTEGER PRIMARY KEY AUTOINCREMENT, run_at TEXT, checked INTEGER, alerted INTEGER, skipped INTEGER);
    CREATE TABLE IF NOT EXISTS forecast_runs (laptop_id TEXT, generated_at TEXT);
    CREATE TABLE IF NOT EXISTS forecast_jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, laptop_id TEXT,
                                              status TEXT, created_at TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS one_open_job_per_laptop ON forecast_jobs(laptop_id)
        WHERE status IN ('queued', 'running');
    CREATE TABLE IF NOT EXISTS operating_mode_state (id INTEGER PRIMARY KEY CHECK (id = 1), mode TEXT, reason TEXT,
                                                     since TEXT, placement_target TEXT, policy_version INTEGER);
    INSERT OR IGNORE INTO operating_mode_state VALUES (1, 'GREEN', 'initial', '1970-01-01T00:00:00+00:00', 'standard', 1);
    """)
    return db


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
            cur = self.db.execute("INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?)", (laptop, retailer, observed_at, price))
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

    def __init__(self, db: sqlite3.Connection, clock: Callable[[], float] = time.monotonic) -> None:
        self.db, self.clock = db, clock
        self._cached: tuple | None = None
        self._at = 0.0

    def current(self) -> tuple[str, str]:
        if self._cached is None or self.clock() - self._at >= PULL_SECONDS:
            mode, target = self.db.execute("SELECT mode, placement_target FROM operating_mode_state WHERE id=1").fetchone()
            self._cached, self._at = (mode, target), self.clock()
        return self._cached

    def on_mode_changed(self, event: Event) -> None:
        self._cached = None
